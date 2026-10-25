import os

EXTENSIONS = ('.py', '.js', '.html', '.css', '.json', '.yml', '.yaml', '.md', '.txt')
EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', 'output', 'data', 'venv', 'env'}
OUTPUT_FILE = 'sourcecode.txt'

def generate_sourcecode():
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        out_f.write('OmniSight Source Code Reference\n')
        out_f.write('===============================\n\n')
        
        for root, dirs, files in os.walk('.'):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
            
            for file in files:
                if file == OUTPUT_FILE or file == 'generate_source.py':
                    continue
                if file.endswith(EXTENSIONS):
                    filepath = os.path.join(root, file)
                    out_f.write(f'--- FILE: {filepath} ---\n')
                    try:
                        with open(filepath, 'r', encoding='utf-8') as in_f:
                            content = in_f.read()
                            out_f.write(content)
                            if not content.endswith('\n'):
                                out_f.write('\n')
                    except Exception as e:
                        out_f.write(f'<Error reading file: {e}>\n')
                    out_f.write('\n')

if __name__ == '__main__':
    generate_sourcecode()
