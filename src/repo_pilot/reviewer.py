from pathlib import Path 
from typing import Any

class PatchReviewer:
    """
    在补丁真正应用之前进行基础安全检查。

    当前版本会检查：

    1. patch 中是否包含 operations。
    2. operation 是否是字典。
    3. operation 类型是否为 replace_text。
    4. path 是否为空。
    5. path 是否为绝对路径。
    6. path 是否尝试跳出仓库目录。
    7. old 和 new 是否为字符串。
    8. new 中是否包含明显危险代码。
    """
    FORBIDDEN_PATH_PARTS={
        ".git",
        "venv",
        "venv-1",
        "__pycache__",
    }

    DANGEROUS_PATTERNS={
        "os.system(",
        "subprocess.Popen(",
        "eval("
        "exec("
        "rm -rf",    
    }

    def review(
            self,
            patch:dict[str,Any],
    )->dict[str,Any]:
        
        issues:list[str]=[]
        operations=patch.get("operations",[])

        if not operations:
            issues.append(
                "Patch does not contain any operations."
            )
        
        for index,operation in enumerate(
            operations,
            start=1,
        ):
            if not isinstance(operation,dict):
                issues.append(
                    f"Operation {index} must be an object."
                )
                continue

            operation_type=operation.get("type")

            if operation_type!="replace_text":
                issues.append(
                    f"Operation{index} has unsupported type:"
                    f"{operation_type}"
                )

            raw_path=operation.get("path")
            
            if not isinstance(raw_path,str):
                issues.append(
                    f"Operation {index} path must be a string."
                )
                continue

            path =Path(raw_path)

            if path.is_absolute():
                issues.append(
                    f"Operation {index} uses an absolute path:"
                    f"{raw_path}"
                )
            if ".." in path.parts:
                issues.append(
                    f"Operation {index} attempts to leaves."
                    f"the repository:{raw_path}"
                ) 
            
            for part in path.parts:
                if  part in self.FORBIDDEN_PATH_PARTS:
                    issues.append(
                        f"Operation {index} targets forbidden"
                        f"directory '{part}':{raw_path}"
            )
            
            old_text=operation.get("old")
            new_text=operation.get("new")

            if not isinstance(old_text,str):
                issues.append(
                    f"Operation {index} old text must be a  string."
                )
            
            if not isinstance(new_text,str):
                issues.append(
                    f"Operation {index} new text must be a string."
                )
                continue
            if(
                isinstance(old_text,str)
                and old_text==new_text):
                issues.append(
                    f"Operation {index} does not change the file."
                )
                
            for pattern in self.DANGEROUS_PATTERNS:
                if pattern in new_text:
                    issues.append(
                        f"Operation {index} coontain dangerous."
                        f"pattern:{pattern}"
                    )
            
        approved=not issues

        return {
            "approved":approved,
            "issues":issues,
        }




            

        
            

    


