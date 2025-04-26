document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('estimativaForm');
    const resultadoDiv = document.getElementById('resultadoPanel'); // Target the panel
    const tabelaBody = document.getElementById('tabelaResultados').querySelector('tbody');
    const btnSalvar = document.getElementById('btnSalvar');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorIndicator = document.getElementById('errorIndicator');
    const promptInput = document.getElementById('prompt');
    const fileInput = document.getElementById('arquivos'); // Get file input

    // Elements to display summary info
    const promptDisplay = document.getElementById('promptDisplay');
    const fileCountDisplay = document.getElementById('fileCount');
    const fileListDisplay = document.getElementById('fileList');

    let currentResults = null; // To store results for CSV download
    let currentPrompt = '';
    let currentFiles = [];

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        resultadoDiv.style.display = 'none'; // Hide previous results
        tabelaBody.innerHTML = ''; // Clear table
        fileListDisplay.innerHTML = ''; // Clear file list
        loadingIndicator.style.display = 'block'; // Show loading
        errorIndicator.style.display = 'none'; // Hide error
        btnSalvar.disabled = true; // Disable save button initially

        const formData = new FormData(form);
        currentPrompt = formData.get('prompt'); // Store current prompt

        try {
            const response = await fetch('/estimativa', {
                method: 'POST',
                body: formData, // FormData handles multipart/form-data encoding
            });

            loadingIndicator.style.display = 'none'; // Hide loading

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({})); // Try to parse error
                console.error('Server Error:', response.status, errorData);
                errorIndicator.textContent = ` ${errorData.error || 'Erro ao processar. Verifique os arquivos e tente novamente.'}`;
                errorIndicator.style.display = 'block'; // Show error
                return; // Stop processing
            }

            const data = await response.json();
            currentResults = data.resultados; // Store results
            currentFiles = data.arquivos_processados || []; // Store processed file names

            // Display Summary Info
            promptDisplay.textContent = currentPrompt;
            fileCountDisplay.textContent = currentFiles.length;
            currentFiles.forEach(fileName => {
                 const li = document.createElement('li');
                 li.textContent = fileName;
                 fileListDisplay.appendChild(li);
            });


            // Populate Table
            currentResults.forEach(r => {
                const row = tabelaBody.insertRow();
                row.insertCell().textContent = r.modelo;
                row.insertCell().textContent = r.input_tokens.toLocaleString(); // Format number
                row.insertCell().textContent = r.output_tokens.toLocaleString();
                row.insertCell().textContent = `$${r.custo.toFixed(5)}`; // Display cost with 5 decimals
            });

            resultadoDiv.style.display = 'flex'; // Show results panel (use flex as defined in CSS)
             if (currentResults && currentResults.length > 0) {
                 btnSalvar.disabled = false; // Enable save button
             }

        } catch (error) {
            console.error('Fetch Error:', error);
            loadingIndicator.style.display = 'none'; // Hide loading
            errorIndicator.textContent = ' Erro de comunicação com o servidor. Tente novamente.';
            errorIndicator.style.display = 'block'; // Show error
        }
    });

    btnSalvar.addEventListener('click', async () => {
        if (!currentResults || !currentPrompt) {
            alert("Não há resultados para salvar ou o prompt está faltando.");
            return;
        }

        btnSalvar.disabled = true; // Disable while processing
        btnSalvar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Salvando...';

        try {
            const payload = {
                prompt: currentPrompt,
                arquivos: currentFiles,
                resultados: currentResults
            };

            const response = await fetch('/download_csv', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                 throw new Error(`Erro ao gerar CSV: ${response.statusText}`);
            }

            // Handle file download
            const blob = await response.blob();
            const contentDisposition = response.headers.get('content-disposition');
            let filename = "estimativa_codex.csv"; // Default filename
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i);
                if (filenameMatch && filenameMatch.length > 1) {
                    filename = filenameMatch[1];
                }
            }

            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename; // Use filename from header or default
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Restore button state
            btnSalvar.disabled = false;
            btnSalvar.innerHTML = '<i class="fas fa-save"></i> Salvar Relatório (CSV)';


        } catch (error) {
            console.error('CSV Download Error:', error);
            alert(`Erro ao salvar CSV: ${error.message}`);
            // Restore button state even on error
             btnSalvar.disabled = false;
             btnSalvar.innerHTML = '<i class="fas fa-save"></i> Salvar Relatório (CSV)';
        }
    });

     // Optional: Clear file input selection if needed on new interaction
     // (Browser security might prevent fully clearing it programmatically)
     fileInput.addEventListener('click', () => {
         // This might not fully clear the selection display in all browsers,
         // but helps signal intent to choose new files.
         fileInput.value = null;
     });
});