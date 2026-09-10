"""CLI entry point for the isolated translation runtime."""
from __future__ import annotations
import os, sys
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from PySide6.QtCore import QCoreApplication
except ImportError:
    QCoreApplication = None
from plugins.translation.worker import TranslationWorker

def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def main():
    app = QCoreApplication(sys.argv) if QCoreApplication is not None else None
    if len(sys.argv) < 2:
        emit({"type":"error","message":"Missing translation request JSON."}); return 2
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        req=json.load(f)
    worker=TranslationWorker(
        segments=req.get("segments", []),
        from_code=req.get("from_code","en"),
        to_code=req.get("to_code","es"),
        install_if_missing=bool(req.get("install_if_missing",True)),
        installation_only=bool(req.get("installation_only",False)),
        model_variant=req.get("model_variant","tiny"),
        transcript=req.get("transcript"),
        variant=req.get("variant"),
        device=req.get("device","cpu"),
    )
    worker.progress.connect(lambda p,m: emit({"type":"progress","percent":p,"message":m}))
    worker.finished.connect(lambda result,key: emit({"type":"finished","result":result,"key":key}))
    worker.cancelled.connect(lambda result,key: emit({"type":"cancelled","result":result,"key":key}))
    worker.error.connect(lambda msg: emit({"type":"error","message":msg}))
    worker.run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
