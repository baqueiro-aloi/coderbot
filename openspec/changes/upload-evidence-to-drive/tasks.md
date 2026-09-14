## 1. Configuration

- [x] 1.1 `EVIDENCE_UPLOAD`, `DRIVE_FOLDER_ID`, `DRIVE_FOLDER_NAME` in `src/config.py`.

## 2. Drive client

- [x] 2.1 `src/drive_client.py`: lazy Google imports, `_folder_id` (configured id or
      find-or-create at My Drive root, cached), `upload_evidence` (resumable upload,
      anyone/reader permission, link returned, best-effort with 403 scope hint).
- [x] 2.2 `tests/test_drive_client.py`: explicit folder, auto folder found/created/
      cached, quote escaping, upload failure, sharing failure, missing/empty file.

## 3. FSM wiring

- [x] 3.1 `main._offload_evidence_video`: mp4-only, timestamped names, drops uploaded
      files, sets `state["evidence_url"]`, leaves failed ones attached.
- [x] 3.2 `finalize_pr`: "Evidence … Video: <link>" body line when uploaded, the old
      "Attached:" sentence otherwise.
- [x] 3.3 `do_push` feedback branch: offload and append `Video: <link>`.
- [x] 3.4 `evidence_url` in `RESET_KEYS`.
- [x] 3.5 `tests/test_evidence_upload.py` covering the helper, `finalize_pr` (link,
      fallback, Newman untouched), the feedback push and `RESET_KEYS`.

## 4. Docs

- [x] 4.1 README Evidence section and OAuth note; `.env.example`; `scripts/setup.sh`
      OAuth wording.
