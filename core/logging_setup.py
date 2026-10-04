"""Structured JSONL logging with size-based rotation."""
from __future__ import annotations
import json,logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
class JsonFormatter(logging.Formatter):
 def format(self,record):
  return json.dumps({"level":record.levelname,"logger":record.name,"message":record.getMessage(),"time":self.formatTime(record)},ensure_ascii=False,separators=(",",":"))
def configure_structured_logging(log_dir:Path,max_bytes:int=5*1024*1024,backup_count:int=5):
 log_dir.mkdir(parents=True,exist_ok=True);handler=RotatingFileHandler(log_dir/"yg.jsonl",maxBytes=max_bytes,backupCount=backup_count,encoding="utf-8");handler.setFormatter(JsonFormatter());logger=logging.getLogger("yg");logger.handlers.clear();logger.addHandler(handler);logger.setLevel(logging.INFO);logger.propagate=False;return logger
