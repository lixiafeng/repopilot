import json
from datetime import datetime
from pathlib import Path
from typing import Any

class TraceRecorder:
    def __init__(self,trace_root:Path):

        run_name=datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        self.run_dir=trace_root/run_name

        self.run_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.events:list[dict[str,Any]]=[]

    def  add(
            self,
            event_type:str,
            payload:dict[str,Any],
    )->None:
        
        event={
            "time":datetime.now().isoformat(),
            "type":event_type,
            "payload":payload,
        }
        self.events.append(event)
        
    def save(self)->Path:

        trace_path=self.run_dir/"trace.json"

        trace_path.write_text(
            json.dumps(
                self.events,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )  

        return trace_path