import json
from pathlib import Path
from typing import Any

from repo_pilot.result import WorkflowResult

class OutputWriter:
    def save(
            self,
            run_dir:Path,
            result:WorkflowResult,
            cost_summary:dict[str,Any],
    )->dict[str,Path|None]:
        run_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        diff_path=self._save_diff(
            run_dir=run_dir,
            diff=result.diff,
        )

        summary_path=self._save_summary(
            run_dir=run_dir,
            result=result,
            cost_summary=cost_summary,
            diff_path=diff_path,
        )

        return{
            "summary":summary_path,
            "diff":diff_path,
        }

    def _save_diff(
            self,
            run_dir,
            diff:str,
    )->Path|None:

        if not diff.strip():
            return None

        diff_path=run_dir/"final.diff"

        diff_path.write_text(
            diff,
            encoding="utf-8",
        )
        return diff_path

    def _save_summary(
            self,
            run_dir:Path,
            result:WorkflowResult,
            cost_summary:dict[str,Any],
            diff_path:Path|None,
    )->Path:
        
        summary_path=run_dir/"summary.json"
        summary={
            "success":result.success,
            "message":result.message,
            "iteration":result.iteration,
            "diff_file":(
                diff_path.name
                if diff_path is not None
                else None
            ),

            "test_output":result.test_output,
            "cost":cost_summary,
        }
        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return summary_path

        
        
