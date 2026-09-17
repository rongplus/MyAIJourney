import argparse

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from auth import get_credentials


def upload(
    video,
    title,
    description,
    category="22",
    privacy="private",
):

    youtube = build(
        "youtube",
        "v3",
        credentials=get_credentials(),
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
        },
    }

    media = MediaFileUpload(
        video,
        chunksize=1024 * 1024,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:
            print(f"{status.progress() * 100:.2f}%")

    print("\nUpload Success!")

    print("Video ID:", response["id"])

    print(
        "https://youtu.be/" + response["id"]
    )

    youtube.thumbnails().set(
    videoId=response["id"],
    media_body=MediaFileUpload(
        'hh.png',
        mimetype="image/png",
    ),
).execute()

    return response["id"]


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument("--video", required=True)

    parser.add_argument("--title", required=True)

    parser.add_argument("--description", default="")

    parser.add_argument(
        "--privacy",
        default="public",
        choices=[
            "private",
            "public",
            "unlisted",
        ],
    )

    args = parser.parse_args()

    video_id = upload(
        args.video,
        args.title,
        args.description,
        privacy=args.privacy,
    )

    