import os
import time
import imaplib
import smtplib
import email
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, formataddr

from openai import OpenAI
client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
CHECK_INTERVAL = int(os.getenv("GMAIL_CHECK_INTERVAL", "30"))

GMAIL_EMAIL = 'huang.rong.bj@gmail.com'
GMAIL_APP_PASSWORD = 'woyx nxro nvdp jtkp'
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


class GmailListener:
    def __init__(self):
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            raise RuntimeError(
                "Environment variables GMAIL_EMAIL and GMAIL_APP_PASSWORD are required."
            )
        self.imap = None
        self.seen_uids = set()

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
    listener = GmailListener()
    listener.run()
