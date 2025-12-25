
boardWidth = 600;


function getPieceColor(piece) {
    switch (piece) {
        case "♔": // White King
        case "♕": // White Queen
        case "♖": // White Rook
        case "♗": // White Bishop
        case "♘": // White Knight
        case "♙": // White Pawn
            return "white";
        case "♚": // Black King
        case "♛": // Black Queen
        case "♜": // Black Rook
        case "♝": // Black Bishop
        case "♞": // Black Knight
        case "♟": // Black Pawn
            return "black";
        default:
            return "none";
    }
}

function _sendBoardState(updatedSquare) {
    let colors = [];
    for (let squareIndex = 0; squareIndex < 64; squareIndex++) {
        const pieceDiv = document.querySelector(`[data-square_index='${squareIndex}'] .chess-piece`);
        if (!pieceDiv) {
            colors[squareIndex] = null;
            continue;
        }

        let dragging = pieceDiv.classList.contains("dragging");
        if (dragging) {
            colors[squareIndex] = null;
            continue;
        }

        colors[squareIndex] = getPieceColor(pieceDiv.innerHTML);
    }
    sendEvent("SquarePieceStateChangeEvent", {
        squares: [updatedSquare],
        colors: colors
    });
}

function _dragOverHandler(e) {
    e.preventDefault();
    e.currentTarget.classList.add("drop-target");
}

function _dragLeaveHandler(e) {
    e.currentTarget.classList.remove("drop-target");
}

function _dragstartHandler(e) {
    const pieceDiv = e.target;
    const fromSquare = pieceDiv.dataset.current_square_index;

    pieceDiv.classList.add("dragging");

    console.log("Drag start:", pieceDiv.innerHTML, "from square", fromSquare);

    e.dataTransfer.setData("text/plain", pieceDiv.innerHTML);
    e.dataTransfer.setData("from-square", fromSquare);

    if (fromSquare < 64) {
        _sendBoardState(parseInt(fromSquare));
    }
}

function _dragendHandler(e) {
    const targetSquare = document.querySelector('.drop-target');

    document.querySelectorAll('.drop-target').forEach(el => el.classList.remove('drop-target'));

    const pieceDiv = e.target;
    const fromSquareIndex = pieceDiv.dataset.current_square_index;
    pieceDiv.classList.remove("dragging");

    if (!targetSquare) {
        console.log("Drag end: dropped outside board, no action taken");
        _sendBoardState(parseInt(fromSquareIndex));
        return;
    }

    const toSquareIndex = targetSquare.dataset.square_index;

    console.log("Drag end: dropping", pieceDiv.innerHTML, "to square", toSquareIndex);

    const fromSquareDiv = document.querySelector(`[data-square_index='${fromSquareIndex}']`);
    const toSquareDiv = document.querySelector(`[data-square_index='${toSquareIndex}']`);

    if (toSquareDiv.innerHTML != "" && toSquareDiv != fromSquareDiv) {
        console.warn("Dragend: target square already occupied, move cancelled.");
        return;
    }

    if (fromSquareDiv && toSquareDiv && pieceDiv) {
        fromSquareDiv.innerHTML = "";
        if (toSquareIndex < 64) {
            toSquareDiv.innerHTML = "";
            toSquareDiv.appendChild(pieceDiv);
            pieceDiv.dataset.current_square_index = toSquareIndex;
            _sendBoardState(parseInt(toSquareIndex));
        }
    }
    else {
        console.error("Error during dragend: could not find source or target square.");
    }
}

function getMissingPieces() {
    // Returns an object with counts of missing pieces for each type and color
    const startingPieces = {
        "♔": 1, "♕": 1, "♖": 2, "♗": 2, "♘": 2, "♙": 8, // White
        "♚": 1, "♛": 1, "♜": 2, "♝": 2, "♞": 2, "♟": 8  // Black
    };

    let currentCounts = {
        "♔": 0, "♕": 0, "♖": 0, "♗": 0, "♘": 0, "♙": 0,
        "♚": 0, "♛": 0, "♜": 0, "♝": 0, "♞": 0, "♟": 0
    };

    document.querySelectorAll('.chess-square').forEach(pieceDiv => {
        const piece = pieceDiv.querySelector('.chess-piece');
        if (piece) {
            const symbol = piece.innerHTML;
            if (symbol in currentCounts) {
                currentCounts[symbol] += 1;
            }
        }
    });

    let missing = {};
    for (const [piece, startCount] of Object.entries(startingPieces)) {
        const diff = startCount - currentCounts[piece];
        if (diff > 0) {
            missing[piece] = diff;
        }
    }
    return missing;
}


function createPieceDiv(pieceSymbol, squareIndex) {
    let pieceDiv = document.createElement("div");
    pieceDiv.className = "chess-piece";
    pieceDiv.dataset.current_square_index = squareIndex;
    pieceDiv.innerHTML = pieceSymbol;
    pieceDiv.setAttribute("draggable", "true");

    pieceDiv.addEventListener("dragstart", _dragstartHandler);
    pieceDiv.addEventListener("dragend", _dragendHandler);

    pieceDiv.style.fontSize = `${boardWidth / 8 * 0.8}px`;
    pieceDiv.style.lineHeight = `${boardWidth / 8}px`;

    return pieceDiv;
}

function updateBoardState() {
    fetch("/api/board/square/pieces")
        .then(response => response.json())
        .then(data => {
            console.log("Fetched piece map data:", data);
            const pieceMap = data.board_state;

            // Clear all pieces from board
            document.querySelectorAll('.chess-square').forEach(square => {
                square.innerHTML = '';
            });

            // Place pieces according to pieceMap
            Object.entries(pieceMap).forEach(([squareIndex, pieceSymbol]) => {
                const squareDiv = document.querySelector(`[data-square_index='${squareIndex}']`);
                if (squareDiv) {
                    const pieceDiv = createPieceDiv(pieceSymbol, squareIndex);
                    squareDiv.appendChild(pieceDiv);
                }
                else {
                    console.error("Could not find square for piece placement:", squareIndex);
                }
            });
        })
        .catch(err => console.error("Failed to fetch piece map data:", err));
}

function updateAllSquareColors() {
    fetch("/api/board/square/colors")
        .then(response => response.json())
        .then(data => {
            console.log("Fetched LED data:", data);
            // data should be { squares: [indices], color: [r, g, b] }
            document.querySelectorAll('.chess-square').forEach(square => {
                square.style.background = ''; // Reset background
                square.style.boxShadow = '';
            });

            Object.entries(data.colors).forEach(([squareIndex, color]) => {
                const squareDiv = document.querySelector(`[data-square_index='${squareIndex}']`);
                if (squareDiv && Array.isArray(color)) {
                    squareDiv.style.background = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
                }
                else {
                    console.error("Could not find square for LED update:", squareIndex);
                }
            });

        })
        .catch(err => console.error("Failed to fetch LED data:", err));
}

function initializeBoard(boardDiv, width) {
    boardWidth = width;

    boardDiv.style.gridTemplateColumns = `repeat(8, ${width / 8}px)`;
    boardDiv.style.gridTemplateRows = `repeat(8, ${width / 8}px)`;
    boardDiv.style.gap = "0";
    boardDiv.style.width = `${width}px`;
    boardDiv.style.height = `${width}px`;
    boardDiv.className = "chess-board";

    for (let row = 0; row < 8; row++) {
        for (let col = 0; col < 8; col++) {
            let square_index = (7 - row) * 8 + col; // Number squares from 0 (a1) to 63 (h8)
            let square_div = document.createElement("div");
            square_div.className = "chess-square";
            square_div.dataset.row = row;
            square_div.dataset.col = col;
            square_div.dataset.square_index = square_index;
            square_div.addEventListener("dragover", _dragOverHandler);
            square_div.addEventListener("dragleave", _dragLeaveHandler);
            boardDiv.appendChild(square_div);
        }
    }

    updateBoardState();
    updateAllSquareColors();

    addBoardEventListener("SetSquareColorEvent", function (data) {
        console.log("LED Change Event data:", data);
        const squareList = data.color_map;
        for (const [squareIndex, color] of Object.entries(squareList)) {
            const squareDiv = document.querySelector(`[data-square_index='${squareIndex}']`);
            if (squareDiv && Array.isArray(color)) {
                squareDiv.style.background = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
                squareDiv.style.boxShadow = '';
            } else {
                console.error("LED Change Event: could not find square", squareIndex);
            }
        }
    });
}
