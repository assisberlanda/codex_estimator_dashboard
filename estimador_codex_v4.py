from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import csv
import tiktoken
import tempfile
from werkzeug.utils import secure_filename
from datetime import datetime
import zipfile
import shutil

app = Flask(__name__)
# Use a dedicated temporary folder for uploads within the app's instance path if possible,
# or stick to system temp if instance path isn't writable.
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'codex_estimator_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Ensure the static folder is correctly configured
app.static_folder = 'static'

PREÇOS = {
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006}, # Updated price 2024-07
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03}, # Often preferred over gpt-4 base
    "gpt-4": {"input": 0.03, "output": 0.06}, # Base gpt-4 is more expensive
}

EXTENSOES_VALIDAS = [".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".txt", ".md", ".yaml", ".yml", ".sh", ".rb", ".php", ".go", ".rs", ".cs", ".cpp", ".c", ".h", ".sql"]

def contar_tokens(texto, modelo="gpt-3.5-turbo"):
    """Counts tokens using tiktoken."""
    try:
        # Use cl100k_base as it's common for recent models
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception as e:
        print(f"Warning: Could not get cl100k_base encoding, falling back. Error: {e}")
        # Fallback if needed, though cl100k_base should be available
        try:
            encoding = tiktoken.encoding_for_model(modelo)
        except:
            # Generic fallback
            return len(texto.split()) # Very rough approximation if tiktoken fails badly

    return len(encoding.encode(texto, disallowed_special=()))

def processar_arquivo(filepath, filename, valid_extensions):
    """Reads content from a file if its extension is valid."""
    if any(filename.lower().endswith(ext) for ext in valid_extensions):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            return None
    return None

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/estimativa', methods=['POST'])
def estimativa():
    """Handles the estimation request."""
    if 'prompt' not in request.form or 'arquivos' not in request.files:
        return jsonify({"error": "Missing prompt or files"}), 400

    prompt = request.form['prompt']
    arquivos = request.files.getlist('arquivos')

    conteudo_total = prompt + "\n\n---\n\n" # Separator for clarity
    arquivos_processados = []
    temp_dirs_to_clean = []

    # Create a unique subfolder for this request's uploads/extractions
    request_temp_dir = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
    temp_dirs_to_clean.append(request_temp_dir)

    for arquivo in arquivos:
        if arquivo.filename == '':
            continue

        filename = secure_filename(arquivo.filename)
        save_path = os.path.join(request_temp_dir, filename)
        arquivo.save(save_path)

        if filename.lower().endswith(".zip"):
            try:
                zip_extract_dir = os.path.join(request_temp_dir, filename + "_extracted")
                os.makedirs(zip_extract_dir, exist_ok=True)
                temp_dirs_to_clean.append(zip_extract_dir) # Mark for cleanup

                with zipfile.ZipFile(save_path, 'r') as zip_ref:
                    zip_ref.extractall(zip_extract_dir)

                # Walk through extracted files
                for root, _, files in os.walk(zip_extract_dir):
                    for file_in_zip in files:
                        # Create a relative path for display/reference
                        relative_path = os.path.relpath(os.path.join(root, file_in_zip), zip_extract_dir)
                        # Secure the relative path components as well
                        safe_relative_path = os.path.join(filename, *[secure_filename(part) for part in relative_path.split(os.sep)])

                        file_path_in_zip = os.path.join(root, file_in_zip)
                        conteudo_arquivo = processar_arquivo(file_path_in_zip, file_in_zip, EXTENSOES_VALIDAS)

                        if conteudo_arquivo is not None:
                            conteudo_total += f"# Arquivo: {safe_relative_path}\n{conteudo_arquivo}\n\n---\n\n"
                            arquivos_processados.append(safe_relative_path)

            except zipfile.BadZipFile:
                print(f"Error: Bad zip file uploaded: {filename}")
                # Optionally inform the user? For now, just skip it.
                continue # Skip processing this file
            except Exception as e:
                print(f"Error processing zip file {filename}: {e}")
                continue # Skip processing this file
            finally:
                # Clean up the original zip file after processing
                 try:
                    os.remove(save_path)
                 except OSError as e:
                     print(f"Error removing temp file {save_path}: {e}")


        else: # Process regular files
            conteudo_arquivo = processar_arquivo(save_path, filename, EXTENSOES_VALIDAS)
            if conteudo_arquivo is not None:
                conteudo_total += f"# Arquivo: {filename}\n{conteudo_arquivo}\n\n---\n\n"
                arquivos_processados.append(filename)
             # Clean up the original uploaded file
            try:
                os.remove(save_path)
            except OSError as e:
                print(f"Error removing temp file {save_path}: {e}")


    input_tokens = contar_tokens(conteudo_total)
    # Keep the fixed estimate, but maybe make it adjustable in the future
    output_tokens_estimado = 800

    resultados = []
    for modelo, precos in PREÇOS.items():
        custo_input = (input_tokens / 1000) * precos["input"]
        custo_output = (output_tokens_estimado / 1000) * precos["output"]
        custo_total = custo_input + custo_output
        resultados.append({
            "modelo": modelo,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens_estimado,
            "custo": round(custo_total, 5) # Use more precision for smaller costs
        })

    # Clean up temporary directories
    for temp_dir in temp_dirs_to_clean:
        try:
            shutil.rmtree(temp_dir)
        except OSError as e:
            print(f"Error removing temporary directory {temp_dir}: {e}")

    return jsonify({
        "resultados": resultados,
        "arquivos_processados": arquivos_processados,
        "prompt": prompt # Return prompt for consistency if needed by JS, though JS already has it
    })

@app.route('/download_csv', methods=['POST'])
def download_csv():
    """Generates and sends the CSV report."""
    try:
        data = request.json
        if not data or 'resultados' not in data or 'prompt' not in data or 'arquivos' not in data:
             abort(400, description="Invalid data format for CSV download.")

        resultados = data['resultados']
        prompt_text = data['prompt']
        arquivos_list = data['arquivos']

        # Use system temp dir for the final CSV
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"estimativa_codex_{timestamp}.csv"
        path = os.path.join(temp_dir, filename)

        with open(path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Write Prompt
            writer.writerow(["Prompt:"])
            # Write prompt line by line to handle multiline prompts better in CSV
            for line in prompt_text.splitlines():
                 writer.writerow([line])
            writer.writerow([]) # Empty row for spacing

            # Write Arquivos
            writer.writerow(["Arquivos Processados:"])
            if arquivos_list:
                for arq in arquivos_list:
                    writer.writerow([arq])
            else:
                writer.writerow(["Nenhum arquivo válido processado."])
            writer.writerow([]) # Empty row for spacing

            # Write Resultados Header
            writer.writerow(["Resultados da Estimativa:"])
            writer.writerow(["Modelo", "Tokens de Entrada", f"Tokens de Saída (Estimados)", "Custo Total (USD)"])

            # Write Resultados Data
            for r in resultados:
                writer.writerow([r["modelo"], r["input_tokens"], r["output_tokens"], f"{r['custo']:.5f}"])

        return send_file(path, as_attachment=True, download_name=filename) # Use download_name

    except Exception as e:
        print(f"Error generating CSV: {e}")
        # Log the error details if possible
        import traceback
        traceback.print_exc()
        abort(500, description="Failed to generate CSV report.")


# Optional: Clean up old files in upload folder on startup or periodically
def cleanup_old_files(folder, max_age_seconds=3600): # Clean files older than 1 hour
    now = datetime.now().timestamp()
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            # Check if it's a file or directory and get its modification time
            file_mod_time = os.path.getmtime(file_path)
            if now - file_mod_time > max_age_seconds:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"Cleaned up old file: {file_path}")
                elif os.path.isdir(file_path):
                     shutil.rmtree(file_path)
                     print(f"Cleaned up old directory: {file_path}")
        except Exception as e:
            print(f"Error during cleanup of {file_path}: {e}")

if __name__ == '__main__':
    # Run cleanup once on startup (optional)
    cleanup_old_files(app.config['UPLOAD_FOLDER'])
    # Use host='0.0.0.0' to make it accessible on the network if needed
    app.run(debug=True, host='0.0.0.0', port=5000)