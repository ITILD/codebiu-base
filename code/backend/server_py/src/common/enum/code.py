"""编程语言代码枚举(编辑器语言/代码高亮等场景)"""

from enum import StrEnum


# class syntax
class CodeType(StrEnum):
    python = "python"
    java = "java"
    cpp = "cpp"
    javascript = "javascript"
    html = "html"
    markdown = "markdown"
    dart = "dart"
    ruby = "ruby"
    c_sharp = "c-sharp"
