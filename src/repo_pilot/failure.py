import re
from pathlib import Path
from typing import Any

from repo_pilot.tools import CommandResult

class FailureAnalyzer:
    FAILED_TEST_RE=re.compile(r"FAILED\s+([^\s])")

    FILE_LINE_RE=re.compile(
        r"(?P<path>(?:[A-Za-z]:)?[^:\s]+\.py):(?P<line>\d+)"
    )
    TRACEBACK_FILE_RE=re.compile(
        r'File\s+"(?P<path>[^"]+\.py)",\s+line\s+(?P<line>\d+)'
    )


    EXCEPTION_RE=re.compile(
        r"^E\s+(?P<type>[A-Za-z_][\w.]*(?:Error|Exception))"
        r"(?::\s*(?P<message>.*))?$",
        re.MULTILINE,
    )

    def analyze(
            self,
            result:CommandResult,
            repo:Path,
    )->tuple[list[dict[str,Any]],list[Path]]:
        output=result.stdout+"\n"+result.stderr

        if result.success:
            return [],[]
        
        failed_tests=self._extract_failed_tests(output) ##找出以FAILED开头的测试节点
        exception_type,exception_message=self._extract_exception(output)
        locations=self._extract_locations(output,repo)


        failures:list[dict[str,Any]]=[
            {
                "exit_code":result.exit_code,
                "timeout":result.timeout,
                "failed_tests":failed_tests,
                "exception_type":exception_type,
                "exception_message":exception_message,
                "locations":locations,
                "summary":self._build_summary(
                    failed_tests=failed_tests,
                    exception_type=exception_type,
                    exception_message=exception_message,
                ),
            }
        ]

        candidates=self._build_candidates(locations)
        return failures,candidates


    def _extract_failed_tests(self,output:str)->list[str]:

        failed_tests:list[str]=[]

        for match in self.FAILED_TEST_RE.finditer(output):
            node_id=match.group(1)

            if node_id not in failed_tests:
                failed_tests.append(node_id)

        return failed_tests
    
    def _extract_exception(self,output:str)->tuple[str|None,str|None]:

        match=self.EXCEPTION_RE.search(output)
        if match is None:
            return None,None
        
        exception_type=match.group("type")
        exception_message=match.group("message")

        return exception_type,exception_message
    
    def _extract_locations(self,
                           output:str,
                           repo:Path,
                           )->list[dict[str:Any]]:
        locations:list[dict[str:Any]]=[]
        seen:set[tuple[str,int]]=set()

        for  match in self.FILE_LINE_RE.finditer(output):
            self._append_location(
                locations=locations,
                seen=seen,
                raw_path=match.group("path"),
                line=int(match.group("line")),
                repo=repo,
            )

        for match in self.TRACEBACK_FILE_RE.finditer(output):
            self._append_location(
                locations=locations,
                seen=seen,
                raw_path=match.group("path"),
                line=int(match.group("line")),
                repo=repo,
            )

        return locations
    
    def _append_location(self,
                         locations:list[dict[str:Any]],
                         seen:set[tuple[str,int]],
                         raw_path:str,
                         line:int,
                         repo:Path,
    )->None:
        
        normalized=raw_path.replace("\\","/")
        path=Path(normalized)

        if path.is_absolute():
            try:
                relative_path=path.resolve().relative_to(repo.resollve())
            except ValueError:

                return
        else:
            relative_path=path

        target=repo/relative_path

        if not target.exists():
            return 
        
        relative_text=relative_path.as_posix()
        key=(relative_text,line)

        if key in seen:
            return
        
        seen.add(key)

        locations.append(
            {
                "file":relative_text,
                "line":line,
            }
        )

    def _build_summary(self,
                       failed_tests:list[str],
                       exception_type:str|None,
                       exception_message:str|None,
                       )->str:
        parts:list[str]=[]

        if exception_type:
            exception_text=exception_type

            if exception_message:
                exception_text+=f":{exception_message}"

        parts.append(exception_text)

        if not parts:
            return "Test command failed,but no structured failure was extracted."
        
        return "; ".join(parts)
    
    def _build_candidates(self,
                          locations:list[dict[str,Any]],
    )->list[Path]:
        
        candidates:list[Path]=[]

        for location in locations:
            path=Path(location["file"])

            if path not in candidates:
                candidates.append(path)

        return candidates
    



        
            
    





    




