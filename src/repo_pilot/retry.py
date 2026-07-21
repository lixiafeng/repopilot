class RetryPolicy:

    RETRYABLE_FAILURES={
        "syntex_error",
        "import_error",
        "assertion_failure",
        "patch_apply_error",
        "unknown_failure",
        "patch_review_error",
    }

    def classify(
            self,
            stage:str,
            output:str,
            error_message:str="",
    )->str:
        combined_text=(
            error_message
            +"\n"
            +output
        ).lower()
        if stage=="patch_review":
            return "patch_review_error"
        

        if(
            stage=="patch_apply"
            or "old text was not found" in combined_text
            or"old text not found" in combined_text
            or "replacement is ambiguous" in combined_text
        ):
            return "patch_apply_error"
        if(
            stage=="compile"
            or "syntax error" in combined_text
            or "indentationerror" in combined_text
        ):
            return "syntex_error" 
        
        if(
            "ModuleNotFoundError" in combined_text
            or"ImportError" in combined_text
        ):
            return "import_error"
        
        if(
            "timeout" in combined_text
            or "timed out" in combined_text
        ):
            return "timeout"
        
        if(
            "assertionerror" in combined_text
            or "failed" in combined_text
        ):
            return "assertion_failure"
        
        return "unknown_failure"
    
    def should_retry(
            self,
            failure_type:str,
            iteration:int,
            max_iterations:int,
    )->bool:
        
        if iteration>=max_iterations:
            return False
        
        return failure_type in self.RETRYABLE_FAILURES
    
        
        


