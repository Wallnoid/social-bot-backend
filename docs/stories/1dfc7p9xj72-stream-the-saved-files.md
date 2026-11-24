## Story
As the Social Bot team, I want the backend to serve the files already saved without loading them whole in memory, so that opening big files does not use the memory of the server.

## Acceptance criteria
- [ ] Given a client's file that is already saved, when a member opens it, then it gets the same bytes, the same type and the same headers as today (`nosniff`, a download with its name when it is not a picture, sound or video), sent in parts and with its size.
- [ ] Given a file that is opened for the first time, when a member opens it, then everything stays as today: it is downloaded from Meta and saved, and the cases of a file that is too big (413), that Meta no longer has (410) or that could not be fetched (502) answer the same.

## Plan
- For a file that is already saved, the open file of the storage is handed over instead of its content, and the response sends it in parts with its size; the file is closed when the response ends.
- The first opening (download from Meta and save) does not change.
- The security and download headers are set the same in both cases.
- Tests: a saved file sent in parts with the same bytes, type, size and headers; the first opening as today; and the existing file tests stay green.

## Out of scope
- Checking the size (`file_size` from Meta) before downloading the bytes: it needs a change in `wanps-core` and stays as another task.
- Changing the limit or the retention of the files.
- Asking for only a part of the file (the `Range` header).

## Suggestions (your call)
- None.
