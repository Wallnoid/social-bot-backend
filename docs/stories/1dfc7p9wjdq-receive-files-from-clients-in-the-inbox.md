## Story
As a business member, I want to see and open the files my clients send me (images, audios, videos, documents and stickers) in the inbox of each channel, so that I can attend to them even when they do not write text.

## Acceptance criteria
- [ ] Given the chat of a client of my business, when I read its messages, then the ones that carry a file say so (its kind and, when they exist, its MIME type and file name), and the others do not.
- [ ] Given a message with a file in a chat of my business, when I open it, then I receive the file: the first time it is requested from Meta and saved, and the following times it is served from what was saved without calling Meta. If the message has no file, belongs to another business or its account is of another business, the API answers that it does not exist; if the file is bigger than 16 MB or Meta no longer has it, it answers a clear error and saves nothing.
- [ ] Given a file saved more than 30 days ago, when the periodic cleanup runs, then it is deleted; and if it is opened again, it is requested from Meta again (or gives the error that it is no longer there).

## Plan
- Reading the messages of a chat marks, for each one, whether it carries a file, using what wanps-core already normalizes.
- A new endpoint per message applies the same business filter as reading the chat; if the file is not saved, it downloads it with wanps-core, checks the cap and saves it; if it is saved, it serves it.
- A small record per saved file (which message it belongs to, where it is, size, MIME type, when it was saved). This adds a table.
- Saving goes through Django's storage interface: disk in the `media` volume now, and S3 later by changing only the configuration.
- A periodic Celery Beat task deletes the files older than 30 days; the retention time and the size cap come from the configuration.

## Out of scope
- Installing and configuring S3 (`django-storages`, `boto3`): only the design is left ready.
- Sending images or audios as a person, and showing previews or thumbnails.
- Transcribing audios, describing images or passing them to the LLM.
- Short-lived signed addresses so that the browser can open the file without headers.
- Frontend changes.

## Decisions made
- Kept 30 days from the moment it is saved, 16 MB cap, disk now and S3 later as configuration only.
- Any member of the business can open a file, as when reading the chat.
- wanps-core downloads the whole file in memory (it has no streaming), so the cap protects the storage but not the memory: a big video still passes through memory before being rejected. Fine for images and audios; to be revisited if big videos matter.
- The endpoint needs `Authorization` and `X-Tenant-ID`, so the frontend asks for the bytes with those headers and shows them as a blob; it cannot use a plain `<img src>`.
- Two simultaneous first opens of the same file both download it from Meta and it is saved once; not worth more machinery now.
- wanps-core 0.6.0 (`get_attachment`, `download_attachment`) is already pinned in this repo.

## Suggestions (your call)
- One single error (410, "the file is no longer available") for "Meta no longer has it" and "it was deleted and Meta does not have it either".
