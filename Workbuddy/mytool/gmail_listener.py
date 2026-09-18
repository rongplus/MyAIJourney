import os
import time
import imaplib
import smtplib
import email
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, formataddr
import time
import asyncio
from autogen_core.models import UserMessage
from autogen_ext.models.ollama import OllamaChatCompletionClient
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
CHECK_INTERVAL = int(os.getenv("GMAIL_CHECK_INTERVAL", "30"))

GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
SEND_REPLIES = os.getenv("GMAIL_SEND_REPLIES", "false").lower() in {"1", "true", "yes"}


def decode_header_value(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def extract_text_from_message(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        for part in message.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        return ""
    else:
        return message.get_payload(decode=True).decode(message.get_content_charset() or "utf-8", errors="replace")

def _fallback_summary(email_text: str) -> str:
    entries = []
    for block in [part.strip() for part in email_text.split("\n---\n") if part.strip()]:
        sender = ""
        subject = ""
        body = ""
        for line in block.splitlines():
            if line.startswith("From:"):
                sender = line.split(":", 1)[1].strip()
            elif line.startswith("Subject:"):
                subject = line.split(":", 1)[1].strip()
            elif line.startswith("Body:"):
                body = line.split(":", 1)[1].strip()
                continue
            elif body:
                body = f"{body}\n{line}".strip()
        clean_body = " ".join(body.split())
        if not subject and sender:
            subject = sender
        if not subject:
            continue
        if len(clean_body) > 220:
            clean_body = clean_body[:220].rstrip() + "..."
        entries.append(f"- {subject} ({sender or 'unknown sender'}): {clean_body}")

def generate_summary(email_text: str) -> str:
    model_name = os.getenv("OLLAMA_MODEL", "llama3.2:3b-instruct-fp16")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    prompt = (
        "Summarize these emails from the Gmail Primary inbox. Group related messages, identify important "
        "decisions, action items, deadlines, and unanswered questions. Keep it concise and use plain text.\n\n"
        f"{email_text}"
    )

    try:
        async def create_reply() -> str:
            client = OllamaChatCompletionClient(
                model=model_name,
                api_key="ollama",
                base_url=base_url,
            )
            try:
                response = await client.create([UserMessage(content=prompt, source="user")])
                if response and getattr(response, "content", None):
                    return response.content.strip()
                return _fallback_summary(email_text)
            finally:
                await client.close()

        summary = asyncio.run(create_reply())
        if summary and summary.strip():
            return summary.strip()
        return _fallback_summary(email_text)
    except Exception as err:
        print(f"⚠️ Ollama failed to generate a summary: {err}")
        return _fallback_summary(email_text)




def simple_reply_generator(subject: str, sender_name: str, sender_email: str, body: str) -> str:
    reply = (
        f"Hi {sender_name or sender_email},\n\n"
        "Thank you for your message. I received your email and will respond shortly after reviewing it.\n\n"
        "Best regards,\n"
        "[Your Name]"
    )
    if len(body) > 0:
        reply = (
            f"Hi {sender_name or sender_email},\n\n"
            "Thanks for your email. I read your message and will follow up as soon as possible.\n\n"
            "Best regards,\n"
            "[Your Name]"
        )
    return reply


def generate_reply(subject: str, sender_name: str, sender_email: str, body: str) -> str:
    prompt = (
        "You are an intelligent email assistant. Compose a polite and concise reply to the following incoming email. "
        "Include a short acknowledgment and the next step if appropriate. Do not include any markup." 
        f"\n\nFrom: {sender_name or sender_email}\nSubject: {subject}\nBody:\n{body}\n"
    )

    try:   
    
        response = client.chat.completions.create(
            model=os.getenv("GMAIL_LLM_MODEL", "llama3.2:3b-instruct-fp16"),
            messages=[{"role": "system", "content":  "You are an intelligent email assistant. Compose a polite and concise reply to the following incoming email. "},
                      {"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        message = response.choices[0].message
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        if not content:
            raise RuntimeError("AI model returned an empty reply")
        return str(content).strip()
    except Exception as error:
        print(f"⚠️ Failed to generate reply using AI model: {error}")
        print("Falling back to simple reply.")
        return simple_reply_generator(subject, sender_name, sender_email, body)


def send_reply(to_address: str, original_message: email.message.Message, body: str) -> None:
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_EMAIL and GMAIL_APP_PASSWORD must be set to send replies.")

    reply = EmailMessage()
    reply["From"] = GMAIL_EMAIL
    reply["To"] = to_address
    subject = decode_header_value(original_message.get("Subject", ""))
    reply["Subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
    if original_message.get("Message-ID"):
        reply["In-Reply-To"] = original_message.get("Message-ID")
        reply["References"] = original_message.get("Message-ID")

    reply.set_content(body)

    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    smtp.starttls()
    smtp.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
    smtp.send_message(reply)
    smtp.quit()


def parse_sender(sender_raw: str) -> tuple[str, str]:
    name, addr = parseaddr(sender_raw)
    return decode_header_value(name), addr


class GmailAgent:
    def __init__(self):
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            raise RuntimeError(
                "Environment variables GMAIL_EMAIL and GMAIL_APP_PASSWORD are required."
            )
        self.imap = None
        self.seen_uids = set()

    def streamChat(self, user_input, history=None, model=None, temperature=None, top_p=None, conversation_id=None):
        del model, temperature, top_p, conversation_id
        display_history = list(history or [])
        display_history.append({"role": "user", "content": user_input})
        display_history.append({"role": "assistant", "content": "正在检查 Gmail Primary inbox..."})
        yield display_history, ""

        try:
            self.connect()
            try:
                uids = self.fetch_unseen_uids() or self.fetch_recent_uids()
                if not uids:
                    result = "Inbox 里当前没有未读邮件，也没有最近 24 小时内的邮件。"
                else:
                    email_text = []
                    for uid in uids:
                        try:
                            message = self.fetch_message_by_uid(uid)
                        except Exception as err:
                            print(f"⚠️ Failed to fetch message UID {uid}: {err}")
                            continue

                        subject = decode_header_value(message.get("Subject", "(no subject)"))
                        sender_name, sender_email = parse_sender(message.get("From", ""))
                        body = extract_text_from_message(message)
                        email_text.append(
                            f"From: {sender_name or sender_email}\n"
                            f"Subject: {subject}\n"
                            f"Body:\n{body}\n"
                        )
                        break

                    if not email_text:
                        result = "没有可读取的邮件内容。"
                    else:
                        result = generate_summary("\n---\n".join(email_text[:1000]))
                display_history[-1]["content"] = result
            finally:
                if self.imap is not None:
                    try:
                        self.imap.logout()
                    except Exception:
                        pass
        except Exception as error:
            display_history[-1]["content"] = f"❌ Gmail 专家调用失败：{error}"
        yield display_history, ""

    def connect(self) -> None:
        self.imap = imaplib.IMAP4_SSL(IMAP_HOST)
        self.imap.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        self.imap.select("INBOX")
        print(f"✅ Connected to Gmail IMAP as {GMAIL_EMAIL}")

    def listServer(self) -> None:
        status, mailboxes = self.imap.list()
        if status != "OK":
            print("⚠️ Failed to list mailboxes.")
            return
        print("📂 Mailboxes:")
        for mailbox in mailboxes:
            print(mailbox.decode("utf-8"))

    def fetch_recent_uids(self) -> list[str]:
        yesterday = datetime.now().astimezone().date() - timedelta(days=1)
        after_date = yesterday.strftime("%Y/%m/%d")
        status, data = self.imap.uid(
            "search",
            None,
            "X-GM-RAW",
            f'"in:inbox category:primary after:{after_date}"',
        )
        if status != "OK":
            return []
        uids = data[0].split()
        return [uid.decode("utf-8") for uid in reversed(uids) if uid]

    def fetch_unseen_uids(self) -> list[str]:
        """Return UIDs of messages that are in the Inbox AND unread.

        Uses Gmail's X-GM-RAW extension with the search syntax
        'in:inbox is:unread' so that unread messages in other labels
        (e.g. archived, Sent, custom labels) are excluded.
        """
        status, _ = self.imap.select("INBOX")
        if status != "OK":
            print("⚠️ Failed to select INBOX, attempting to reconnect...")
            self.connect()
            return []

        # Gmail-specific IMAP extension: X-GM-RAW lets us use Gmail search
        # operators directly, which reliably constrains results to Inbox.
        # NB: imaplib does NOT auto-quote args containing spaces, so we
        # must embed literal double-quotes in the search string.
        status, data = self.imap.uid(
            "search", None, "X-GM-RAW", '"in:inbox is:unread category:primary"'
        )
        if status != "OK":
            return []
        uids = data[0].split()
        return [uid.decode("utf-8") for uid in reversed(uids)  if uid]

    def fetch_message_by_uid(self, uid: str) -> email.message.Message:
        status, data = self.imap.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data:
            raise RuntimeError(f"Failed to fetch message UID {uid}: status={status} data={data!r}")

        raw_message = None
        first_item = data[0]
        if isinstance(first_item, tuple) and len(first_item) > 1:
            raw_message = first_item[1]
        elif isinstance(first_item, bytes):
            raw_message = first_item
        elif len(data) > 1 and isinstance(data[1], bytes):
            raw_message = data[1]

        if not raw_message:
            raise RuntimeError(f"Failed to fetch message UID {uid}: unexpected IMAP response {data!r}")

        return email.message_from_bytes(raw_message)

    def mark_as_seen(self, uid: str) -> None:
        self.imap.uid("store", uid, "+FLAGS", "(\SEEN)")


    def run(self) -> None:
        self.connect()
        try:
            uids = self.fetch_unseen_uids() or self.fetch_recent_uids()
            print(f"🔍 Found {len(uids)} recent Primary inbox email(s) to process.")
            email_text = []

            for uid in uids:
                try:
                    message = self.fetch_message_by_uid(uid)
                except Exception as err:
                    print(f"⚠️ Failed to fetch message UID {uid}: {err}")
                    continue

                subject = decode_header_value(message.get("Subject", "(no subject)"))
                sender_name, sender_email = parse_sender(message.get("From", ""))
                body = extract_text_from_message(message)
                print(f"📬 {subject} | From: {sender_name or sender_email}")
                email_text.append(
                    f"From: {sender_name or sender_email}\n"
                    f"Subject: {subject}\n"
                    f"Body:\n{body}\n"
                )

            if email_text:
                print(f"\n📝 Summary of emails from yesterday to now:\n {email_text} \n")
                ret = (generate_summary("\n---\n".join(email_text[0:1000])))
                print(f"Summary:\n{ret}")
            else:
                print("No Primary inbox emails found since yesterday.")
        finally:
            if self.imap is not None:
                self.imap.logout()


    def run1(self) -> None:
        self.connect()
        print("⏳ Waiting for new email messages...")
        #self.listServer()
        print("ℹ️ Note: Only new messages in the Inbox that are unread will be processed.")

        while True:
            try:
                unseen_uids = self.fetch_unseen_uids()
                new_uids = [uid for uid in unseen_uids if uid not in self.seen_uids]
                print(f"🔍 Found {len(new_uids)} new unseen email(s).")

                for uid in new_uids:
                    try:
                        message = self.fetch_message_by_uid(uid)
                    except Exception as err:
                        print(f"⚠️ Failed to fetch message UID {uid}: {err}")
                        continue

                    subject = decode_header_value(message.get("Subject", "(no subject)"))
                    sender_name, sender_email = parse_sender(message.get("From", ""))
                    body = extract_text_from_message(message)

                    print("\n📬 New email received!")
                    print(f"From: {sender_name or sender_email}")
                    print(f"Subject: {subject}")
                    print(f"Preview: {body[:240].strip()}\n")

                    reply_body = generate_reply(subject, sender_name, sender_email, body)
                    print("📝 Generated reply:\n")
                    print(reply_body)

                    if SEND_REPLIES:
                        try:
                            send_reply(sender_email, message, reply_body)
                            print("✉️ Reply sent successfully.")
                        except Exception as err:
                            print(f"⚠️ Failed to send reply: {err}")

                    self.mark_as_seen(uid)
                    self.seen_uids.add(uid)
                    

                time.sleep(CHECK_INTERVAL)
            except imaplib.IMAP4.abort:
                print("⚠️ IMAP connection aborted, reconnecting...")
                self.connect()
            except Exception as exc:
                print(f"⚠️ Listener error: {exc}")
                time.sleep(CHECK_INTERVAL)

            break


if __name__ == "__main__":
    print("Gmail monitor starting...")
    listener = GmailAgent()
    listener.run()
    #ret = generate_summary("Nearly two years after a bipartisan task force issued 85 recommendations for how lawmakers could address the technology, there are still few federal laws governing its rapid development. It’s not for a lack of ideas: Lawmakers in both parties have introduced proposals ranging from safeguards for powerful AI models to requiring companies to build a “kill switch” into their technology, but many have stalled in committees without reaching the House or Senate floor.")
    #print (f"Summary:\n{ret}")
