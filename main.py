import os

def load_env():
    try:
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    # Don't overwrite if already set in environment
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip().strip('"\'')
    except FileNotFoundError:
        pass

if __name__ == "__main__":
    load_env()
    from app.runtime.telegram.bot_runtime import main
    main()
