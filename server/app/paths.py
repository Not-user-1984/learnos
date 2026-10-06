import pathlib

SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent
DATA_DIR = REPO_DIR / "data"
DB_PATH = DATA_DIR / "learnos.db"
KB_DIR = REPO_DIR / "kb"
SKILLS_DIR = SERVER_DIR / "skills"

DATA_DIR.mkdir(exist_ok=True)
KB_DIR.mkdir(exist_ok=True)
