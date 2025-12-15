// Text input state
let keyboardRow = 0;
let keyboardCol = 0;
let keyboardInput = '';
let keyboardCallback = null;

// Virtual keyboard layout
const keyboardLayoutNormal = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', '-'],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm', '_', '.', '@'],
    ['?!@', '', 'SPACE', '', 'DEL', '', 'CLEAR', '', 'DONE', '']
];

const keyboardLayoutUppercase = [
    ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')'],
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', '+'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', '{', '}', '?'],
    ['?!@', '', 'SPACE', '', 'DEL', '', 'CLEAR', '', 'DONE', '']
]
// Number keyboard layout for custom time input
const keyboardLayoutNumber = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['0', 'DEL', 'DONE']
];

const specialKeys = {
    'SPACE': ' ',
    'DEL': 'DEL',
    'CLEAR': 'CLEAR',
    'DONE': 'DONE',
    'SHIFT': 'SHIFT'
};

let currentKeyboardLayout = keyboardLayoutNormal;

// Generate keyboard grid
function generateKeyboard() {
    const grid = document.getElementById('keyboard-grid');
    grid.innerHTML = '';

    // Create table for keyboard grid
    var table = document.createElement('table');
    table.className = 'keyboard-table';
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.tableLayout = 'fixed';

    currentKeyboardLayout.forEach(function (row, rowIndex) {
        var tr = document.createElement('tr');
        tr.className = 'keyboard-row';
        for (var colIndex = 0; colIndex < row.length; colIndex++) {
            var key = row[colIndex];
            if (key === '') continue; // skip empty keys, handled by colspan
            var td = document.createElement('td');
            td.className = 'keyboard-key';
            td.textContent = key;
            td.dataset.row = rowIndex;
            td.dataset.col = colIndex;

            td.style.background = '#3a3a3a';
            td.style.padding = '6px 2px';
            td.style.textAlign = 'center';
            td.style.border = '2px solid #5a5a5a';
            td.style.borderRadius = '3px';
            td.style.fontSize = '10px';
            td.style.fontWeight = 'bold';
            td.style.cursor = 'pointer';

            // Calculate colspan for consecutive '' keys
            var colspan = 1;
            for (var next = colIndex + 1; next < row.length && row[next] === ''; next++) {
                colspan++;
            }
            if (colspan > 1) {
                td.colSpan = colspan;
                td.style.width = (100 / row.length * colspan) + '%';
            } else {
                td.style.width = (100 / row.length) + '%';
            }
            tr.appendChild(td);
            colIndex += (colspan - 1); // skip spanned columns
        }
        table.appendChild(tr);
    });
    grid.appendChild(table);

    const display = document.getElementById('keyboard-input-display');
    display.textContent = keyboardInput;

    keyboardUpdateSelection();
}

// Update keyboard key selection highlight
function keyboardUpdateSelection() {
    const keys = Array.from(document.querySelectorAll('.keyboard-key'));
    keys.forEach(key => {
        const row = parseInt(key.dataset.row);
        const col = parseInt(key.dataset.col);
        if ((row === keyboardRow) && (col === keyboardCol)) {
            key.style.background = 'linear-gradient(135deg, #f5f5f5, #e0e0e0)';
            key.style.color = '#1a1a1a';
            key.style.borderColor = '#d4af37';
            key.style.boxShadow = '0 0 8px rgba(212, 175, 55, 0.6)';
        } else {
            key.style.background = '#3a3a3a';
            key.style.color = '#f5f5f5';
            key.style.borderColor = '#5a5a5a';
            key.style.boxShadow = 'none';
        }
    });

    // Update action buttons
    const actions = Array.from(document.querySelectorAll('.keyboard-action'));
    actions.forEach(action => action.style.opacity = '0.6');
}

function keyboardMoveRight() {
    keyboardCol = (keyboardCol + 1) % currentKeyboardLayout[keyboardRow].length;
    if (currentKeyboardLayout[keyboardRow][keyboardCol] === '') {
        // Skip empty keys
        keyboardMoveRight();
        return;
    }
    keyboardUpdateSelection();
}

function keyboardMoveLeft() {
    keyboardCol = (keyboardCol - 1 + currentKeyboardLayout[keyboardRow].length) % currentKeyboardLayout[keyboardRow].length;
    if (currentKeyboardLayout[keyboardRow][keyboardCol] === '') {
        // Skip empty keys
        keyboardMoveLeft();
        return;
    }
    keyboardUpdateSelection();
}

function keyboardMoveUp() {
    keyboardRow = (keyboardRow - 1 + currentKeyboardLayout.length) % currentKeyboardLayout.length;
    keyboardCol = Math.min(keyboardCol, currentKeyboardLayout[keyboardRow].length - 1);
    if (currentKeyboardLayout[keyboardRow][keyboardCol] === '') {
        // Skip empty keys
        keyboardMoveLeft();
        return;
    }
    keyboardUpdateSelection();
}

function keyboardMoveDown() {
    keyboardRow = (keyboardRow + 1) % currentKeyboardLayout.length;
    keyboardCol = Math.min(keyboardCol, currentKeyboardLayout[keyboardRow].length - 1);
    if (currentKeyboardLayout[keyboardRow][keyboardCol] === '') {
        // Skip empty keys
        keyboardMoveLeft();
        return;
    }
    keyboardUpdateSelection();
}

function keyboardGetSelectedKey() {
    return currentKeyboardLayout[keyboardRow][keyboardCol];
}
