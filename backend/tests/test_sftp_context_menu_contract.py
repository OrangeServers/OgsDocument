from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FILE_TRANSFER = ROOT / "frontend" / "src" / "views" / "FileTransfer.vue"


def test_sftp_row_action_button_stops_document_click_propagation():
    source = FILE_TRANSFER.read_text(encoding="utf-8")
    assert (
        '@click.stop="showContextMenu($event, row)"' in source
    ), (
        "the row action click must not reach the document listener that "
        "immediately closes the context menu"
    )


def test_sftp_cancelled_confirmations_do_not_leak_unhandled_rejections():
    source = FILE_TRANSFER.read_text(encoding="utf-8")
    assert "async function doDelete(row: FileEntry): Promise<void> {\n  try {" in source
    assert "async function doRename(row: FileEntry): Promise<void> {\n  let value: string\n  try {" in source
