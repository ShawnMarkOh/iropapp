document.addEventListener('DOMContentLoaded', () => {
    const dbSelect = document.getElementById('db-select');
    const tableSelect = document.getElementById('table-select');
    const dataDisplay = document.getElementById('data-display');
    const tableHeading = document.getElementById('table-heading');
    const tableContainer = document.getElementById('table-container');
    const statusContainer = document.getElementById('status-container');
    const paginationTop = document.getElementById('pagination-controls-top');
    const paginationBottom = document.getElementById('pagination-controls-bottom');
    const editModalEl = document.getElementById('edit-modal');
    const editModal = new bootstrap.Modal(editModalEl);
    const editForm = document.getElementById('edit-form');
    const saveChangesBtn = document.getElementById('save-changes-btn');

    let currentBind = null;
    let currentTable = null;
    let currentPage = 1;
    let currentEntryId = null;

    function showAlert(message, type = 'danger') {
        statusContainer.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>`;
    }

    async function loadBinds() {
        try {
            const response = await fetch('/api/admin/db/binds');
            if (!response.ok) throw new Error('Failed to load databases.');
            const binds = await response.json();
            dbSelect.innerHTML = '<option selected disabled>Choose...</option>';
            binds.forEach(bind => {
                const option = new Option(bind === 'default' ? 'weatherlog.db' : `${bind}.db`, bind);
                dbSelect.add(option);
            });
        } catch (error) {
            showAlert(error.message);
        }
    }

    async function loadTables(bind) {
        try {
            tableSelect.innerHTML = '<option selected disabled>Loading...</option>';
            tableSelect.disabled = true;
            const response = await fetch(`/api/admin/db/tables/${bind}`);
            if (!response.ok) throw new Error('Failed to load tables.');
            const tables = await response.json();
            tableSelect.innerHTML = '<option selected disabled>Choose...</option>';
            tables.forEach(table => {
                const option = new Option(table, table);
                tableSelect.add(option);
            });
            tableSelect.disabled = false;
        } catch (error) {
            showAlert(error.message);
            tableSelect.innerHTML = '<option selected disabled>Error loading tables</option>';
        }
    }

    async function loadData(bind, table, page = 1) {
        currentBind = bind;
        currentTable = table;
        currentPage = page;
        try {
            dataDisplay.style.display = 'block';
            tableHeading.textContent = `Table: ${table}`;
            tableContainer.innerHTML = '<div class="text-center p-5"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';
            
            const response = await fetch(`/api/admin/db/table/${bind}/${table}?page=${page}`);
            if (!response.ok) throw new Error(`Failed to load data for table ${table}.`);
            const data = await response.json();

            renderTable(data.columns, data.items);
            renderPagination(data);
        } catch (error) {
            showAlert(error.message);
            dataDisplay.style.display = 'none';
        }
    }

    function renderTable(columns, items) {
        if (items.length === 0) {
            tableContainer.innerHTML = '<p class="text-center text-muted mt-3">No entries found in this table.</p>';
            return;
        }
        let head = '<tr>';
        columns.forEach(col => head += `<th>${col}</th>`);
        head += '<th>Actions</th></tr>';

        let body = '';
        items.forEach(item => {
            body += `<tr data-id="${item.id}">`;
            columns.forEach(col => {
                let value = item[col];
                let displayValue = value;
                if (typeof value === 'string' && value.length > 50) {
                    displayValue = value.substring(0, 50) + '...';
                } else if (value === null) {
                    displayValue = '<em>NULL</em>';
                } else if (typeof value === 'boolean') {
                    displayValue = value ? '✔️' : '❌';
                }
                body += `<td class="truncate" title="${value}">${displayValue}</td>`;
            });
            body += `<td>
                <button class="btn btn-sm btn-primary edit-btn" data-id="${item.id}">Edit</button>
                <button class="btn btn-sm btn-danger delete-btn" data-id="${item.id}">Delete</button>
            </td>`;
            body += '</tr>';
        });

        tableContainer.innerHTML = `<table class="table table-sm table-bordered table-hover"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    }

    function renderPagination(data) {
        if (data.total_pages <= 1) {
            paginationTop.innerHTML = '';
            paginationBottom.innerHTML = '';
            return;
        }
        let html = `<ul class="pagination pagination-sm">`;
        html += `<li class="page-item ${!data.has_prev ? 'disabled' : ''}"><a class="page-link" href="#" data-page="${data.page - 1}">Previous</a></li>`;
        for (let i = 1; i <= data.total_pages; i++) {
            html += `<li class="page-item ${i === data.page ? 'active' : ''}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
        }
        html += `<li class="page-item ${!data.has_next ? 'disabled' : ''}"><a class="page-link" href="#" data-page="${data.page + 1}">Next</a></li>`;
        html += `</ul>`;
        paginationTop.innerHTML = html;
        paginationBottom.innerHTML = html;
    }

    function openEditModal(item, columns) {
        currentEntryId = item.id;
        editForm.innerHTML = '';
        columns.forEach(col => {
            if (col === 'id') return; // Don't allow editing ID

            const value = item[col];
            const type = typeof value;
            let inputHtml = '';

            const label = `<label for="edit-${col}" class="form-label">${col}</label>`;

            if (type === 'boolean') {
                inputHtml = `<select class="form-select" id="edit-${col}" data-col="${col}">
                    <option value="true" ${value ? 'selected' : ''}>True</option>
                    <option value="false" ${!value ? 'selected' : ''}>False</option>
                </select>`;
            } else if (type === 'number') {
                inputHtml = `<input type="number" class="form-control" id="edit-${col}" value="${value || ''}" data-col="${col}">`;
            } else if (typeof value === 'string' && value.length > 100) {
                inputHtml = `<textarea class="form-control" id="edit-${col}" rows="4" data-col="${col}">${value || ''}</textarea>`;
            } else {
                inputHtml = `<input type="text" class="form-control" id="edit-${col}" value="${value || ''}" data-col="${col}">`;
            }
            editForm.innerHTML += `<div class="mb-3">${label}${inputHtml}</div>`;
        });
        editModal.show();
    }

    async function saveChanges() {
        const data = {};
        editForm.querySelectorAll('[data-col]').forEach(input => {
            data[input.dataset.col] = input.value;
        });

        try {
            const response = await fetch(`/api/admin/db/table/${currentBind}/${currentTable}/${currentEntryId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Failed to save changes.');
            
            editModal.hide();
            showAlert('Entry updated successfully.', 'success');
            loadData(currentBind, currentTable, currentPage);
        } catch (error) {
            showAlert(error.message);
        }
    }

    async function deleteEntry(id) {
        if (!confirm(`Are you sure you want to delete entry with ID ${id}? This cannot be undone.`)) {
            return;
        }
        try {
            const response = await fetch(`/api/admin/db/table/${currentBind}/${currentTable}/${id}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Failed to delete entry.');
            
            showAlert('Entry deleted successfully.', 'success');
            loadData(currentBind, currentTable, currentPage);
        } catch (error) {
            showAlert(error.message);
        }
    }

    // Event Listeners
    dbSelect.addEventListener('change', () => {
        currentBind = dbSelect.value;
        tableSelect.innerHTML = '<option selected disabled>Select a database first</option>';
        dataDisplay.style.display = 'none';
        if (currentBind) {
            loadTables(currentBind);
        }
    });

    tableSelect.addEventListener('change', () => {
        currentTable = tableSelect.value;
        if (currentBind && currentTable) {
            loadData(currentBind, currentTable, 1);
        }
    });

    document.addEventListener('click', e => {
        if (e.target.matches('#pagination-controls-top a, #pagination-controls-bottom a')) {
            e.preventDefault();
            const page = e.target.dataset.page;
            if (page) {
                loadData(currentBind, currentTable, parseInt(page));
            }
        }
        if (e.target.matches('.edit-btn')) {
            const id = e.target.dataset.id;
            const row = e.target.closest('tr');
            const cells = row.querySelectorAll('td');
            const columns = Array.from(tableContainer.querySelectorAll('th')).map(th => th.textContent);
            columns.pop(); // remove 'Actions' column
            const item = {};
            columns.forEach((col, i) => {
                item[col] = cells[i].title; // Use full value from title
            });
            item.id = id;
            openEditModal(item, columns);
        }
        if (e.target.matches('.delete-btn')) {
            const id = e.target.dataset.id;
            deleteEntry(id);
        }
    });

    saveChangesBtn.addEventListener('click', saveChanges);

    // Initial load
    loadBinds();
});
