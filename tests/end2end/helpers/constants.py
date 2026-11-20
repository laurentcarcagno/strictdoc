# Using XPATH to search text containing &nbsp;
# https://stackoverflow.com/a/59699055
NBSP = "\u00a0"

TEXT_WITH_TRAILING_WHITESPACES = """
Hello world!    
    
Hello world!    
    
Hello world!    
                """  # noqa: W291, W293
