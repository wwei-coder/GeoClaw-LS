import os
import ast
import sys
# 常用库映射表：Import Name -> PyPI Package Name
PACKAGE_MAPPING = {
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "docx": "python-docx",
    "fitz": "pymupdf",
    "faiss": "faiss-cpu",
    "sentence_transformers": "sentence-transformers",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "seaborn": "seaborn",
    "mplcursors": "mplcursors",
    # 标准库或特殊处理
    "tkinter": None,
    "typing": None,
    "collections": None,
    "json": None,
    "os": None,
    "sys": None,
    "re": None,
    "math": None,
    "time": None,
    "datetime": None,
    "random": None,
    "pickle": None,
    "shutil": None,
    "pathlib": None,
    "threading": None,
    "queue": None,
    "subprocess": None,
    "difflib": None,
    "ast": None,
    "abc": None,
    "enum": None,
    "io": None,
    "logging": None,
    "unittest": None,
    "functools": None,
    "platform": None,
    "sqlite3": None,
    "inspect": None,
    "traceback": None,
    "warnings": None,
    "contextlib": None,
    "hashlib": None,
    "tempfile": None,
    "glob": None,
    "argparse": None,
    "copy": None,
    "csv": None,
    "urllib": None,
    "http": None,
    "email": None,
    "xml": None,
    "html": None,
    "socket": None,
    "signal": None,
    "weakref": None,
    "gc": None,
    "site": None,
    "builtins": None,
    "types": None,
    "struct": None,
    "textwrap": None,
    "statistics": None,
    "operator": None,
    "itertools": None,
}

def get_stdlib_modules():
    """获取标准库列表"""
    if sys.version_info[:2] >= (3, 10):
        return sys.stdlib_module_names
    else:
        import distutils.sysconfig as sysconfig
        std_lib = sysconfig.get_python_lib(standard_lib=True)
        return set(os.listdir(std_lib))

STDLIB_MODULES = get_stdlib_modules()

def scan_imports(root_dir):
    imports = set()
    for root, _dirs, files in os.walk(root_dir):
        if ".venv" in root or "__pycache__" in root or ".git" in root or ".idea" in root:
            continue
            
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                        
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for name in node.names:
                                imports.add(name.name.split('.')[0])
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports.add(node.module.split('.')[0])
                except Exception as e:
                    print(f"Warning: Could not parse {path}: {e}")
    return imports

def generate_requirements():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Scanning project at: {base_dir}")
    
    raw_imports = scan_imports(base_dir)
    requirements = set()
    
    for imp in raw_imports:
        if imp in PACKAGE_MAPPING:
            pkg = PACKAGE_MAPPING[imp]
            if pkg is not None:
                requirements.add(pkg)
            continue
            
        if imp in STDLIB_MODULES:
            continue
        if imp in sys.builtin_module_names:
            continue
            
        local_dirs = {d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))}
        if imp in local_dirs:
            continue
            
        if imp and not imp.startswith('_'):
             requirements.add(imp)

    # 处理隐式依赖
    if "pandas" in requirements:
        requirements.add("openpyxl")
        requirements.add("tabulate")
        
    if "sentence-transformers" in requirements or "sentence_transformers" in requirements:
        if "torch" not in requirements:
            requirements.add("torch")

    if "matplotlib" in requirements:
        requirements.add("seaborn")
        requirements.add("mplcursors")

    req_list = sorted(list(requirements))
    output_path = os.path.join(base_dir, "requirements.txt")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(req_list))
        
    print(f"Generated requirements.txt with {len(req_list)} packages.")
    print("Content:")
    print("\n".join(req_list))

if __name__ == "__main__":
    generate_requirements()
