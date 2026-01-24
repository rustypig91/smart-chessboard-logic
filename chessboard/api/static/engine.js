export class StockfishEngine {
    constructor(options = {}) {
        this.workerUrl = options.workerUrl || '/static/node_modules/stockfish/src/stockfish-17.1-8e4d048.js';
        this.numThreads = options.numThreads || navigator.hardwareConcurrency || 4;
        this.worker = new Worker(this.workerUrl);

        this.queue = new AsyncQueue();

        // this.worker.addEventListener('message', (event) => {
        //     console.log('Stockfish message:', event.data);
        // });

        this._postMessageToQueue('uci', 'uciok', null, null);
        this._postMessageToQueue('isready', 'readyok', null, null);
        this._postMessageToQueue(`setoption name Threads value ${this.numThreads}`);

        this.analyzeCache = {};
    }

    _postMessageToQueue(message, response = '', lineCallback = null, doneCallback = null) {
        return this.queue.enqueue(() => this._postMessage(message, response, lineCallback, doneCallback));
    }

    // Send a message to the engine and wait for a specific response
    async _postMessage(message, response = '', lineCallback = null, doneCallback = null) {
        console.log('Sending to engine:', message);
        this.worker.postMessage(message);
        if (!response) {
            if (doneCallback) {
                doneCallback();
            }
            return;
        }

        return new Promise((resolve) => {
            const handleMessage = (event) => {
                const data = event.data;
                if (lineCallback) {
                    lineCallback(data);
                }
                if (data.startsWith(response)) {
                    this.worker.removeEventListener('message', handleMessage);
                    resolve(data);
                    if (doneCallback) {
                        doneCallback(data);
                    }
                    console.log('Received from engine:', data);
                }
            };
            this.worker.addEventListener('message', handleMessage);
        });
    }

    _parsePgnMoves(pgnText) {
        const moves = [];
        const moveRegex = /\b([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?|O-O(-O)?)\b/g;
        let match;
        while ((match = moveRegex.exec(pgnText)) !== null) {
            moves.push(match[1]);
        }
        return moves;
    }

    async _position(fen = "startpos", moves = []) {
        const uciMoves = moves.map(move => move_to_uci(move));
        let move_cmd = '';
        if (uciMoves.length > 0) {
            move_cmd = ' moves ' + uciMoves.join(' ');
        }

        let fen_cmd = '';
        if (fen === "startpos") {
            fen_cmd = ` ${fen}`;
        } else if (fen) {
            fen_cmd = ` fen ${fen}`;
        }

        const positionCommand = `position${fen_cmd}${move_cmd}`;
        await this._postMessage(positionCommand);
    }

    async _go(depth = 32, infoCallback = null, bestMoveCallback = null) {
        return new Promise((resolve, reject) => {
            this._postMessage(`go depth ${depth}`, 'bestmove', (infoResponse) => {
                if (infoResponse.startsWith('info ') && infoCallback) {
                    infoCallback(new Info(infoResponse));
                }
            }, (bestmoveResponse) => {
                const bestMove = new BestMove(bestmoveResponse);
                resolve({ bestMove });
                if (bestMoveCallback) {
                    bestMoveCallback(bestMove);
                }
            });
        });
    }

    async _stop() {
        return this._postMessage('stop');
    }

    async stop() {
        this.queue.clear();
        return this._postMessage('stop');
    }

    async _analyzePosition(startpos = "startpos", moves = [], depth = 32, infoCallback = null, bestMoveCallback = null) {
        await this._stop();
        await this._position(startpos, moves);
        return this._go(depth, infoCallback, bestMoveCallback);
    }

    async analyzeGame(moves = [], depth = 32) {
        const resultPromises = [];
        let currentMoves = [];

        // Initial position
        resultPromises.push(this._analyzePosition("startpos", currentMoves.slice(), depth, true));

        for (const move of moves) {
            currentMoves.push(move_to_uci(move));
            resultPromises.push(this._analyzePosition("startpos", currentMoves.slice(), depth, false));
        }

        return Promise.all(resultPromises);
    }

    _startNewGame() {
        this._postMessageToQueue('ucinewgame');
        this._postMessageToQueue('isready', 'readyok');
    }

    async analyzePgnGame(pgnText, depth = 32, analysisCallback) {
        let chess = new Chess();
        chess.load_pgn(pgnText);
        const moves = chess.history({ verbose: true });

        this._startNewGame();

        let currentChess = new Chess();

        let promises = [];


        for (let i = 0; i <= moves.length; i++) {
            let currentMoves = moves.slice(0, i);
            let fen = currentChess.fen();
            let lastMove = i > 0 ? currentMoves[i - 1] : null;
            const promise = this.queue.enqueue(() => {
                return this._analyzePosition("startpos", currentMoves, depth,
                    (info) => {
                        analysisCallback({
                            moveIndex: i,
                            info: info,
                            moves: currentMoves,
                            fen: fen,
                            lastMove: lastMove,
                        });
                    }, null);
            });

            promises.push(promise);
            currentChess.move(moves[i]);
        }

        return Promise.all(promises);
    }
}

class BestMove {
    constructor(text) {
        const parts = text.split(' ');
        this.raw = text;
        this.uci = parts[1];
        this.ponder = parts[3] || null;
    }
}


class Info {
    constructor(text) {
        // Parse an 'info' line from Stockfish into a structured object
        // Example: info depth 20 seldepth 33 multipv 1 score cp 13 nodes 123456 nps 12345 time 100 pv e2e4 e7e5 ...
        this.raw = text;
        const tokens = text.trim().split(/\s+/);
        const getNum = (key) => {
            const i = tokens.indexOf(key);
            if (i >= 0 && i + 1 < tokens.length) {
                const n = Number(tokens[i + 1]);
                return Number.isFinite(n) ? n : undefined;
            }
            return undefined;
        };

        this.depth = getNum('depth');
        this.seldepth = getNum('seldepth');
        this.multipv = getNum('multipv') ?? 1;
        this.nodes = getNum('nodes');
        this.nps = getNum('nps');
        this.time = getNum('time');

        this.score = { type: null, value: null };

        const si = tokens.indexOf('score');
        if (si >= 0 && si + 2 < tokens.length) {
            const type = tokens[si + 1];
            const valRaw = tokens[si + 2];
            const value = Number(valRaw);
            if (Number.isFinite(value)) {
                if (type === 'mate') {
                    this.score = { type: 'mate', value: value };
                } else if (type === 'cp') {
                    this.score = { type: 'cp', value: value };
                }
            }
        }


        this.pv = [];
        const pvi = tokens.indexOf('pv');
        if (pvi >= 0 && pvi + 1 < tokens.length) {
            this.pv = tokens.slice(pvi + 1);
        }
    }
};


class AsyncQueue {
    constructor() {
        this.queue = [];
        this.running = false;
        this.clearRequested = false;
    }

    enqueue(asyncFn) {
        return new Promise((resolve, reject) => {
            this.queue.push({ asyncFn, resolve, reject });
            this.run();
        });
    }

    async clear() {
        this.clearRequested = true;
    }

    async run() {
        if (this.running) return;
        this.running = true;

        while (this.queue.length) {
            const { asyncFn, resolve, reject } = this.queue.shift();
            if (this.clearRequested) {
                reject('AsyncQueue cleared');
                continue;
            }

            try {
                const result = await asyncFn();
                resolve(result);
            } catch (err) {
                reject(err);
            }
        }

        this.running = false;
        this.clearRequested = false;
    }
}
window.StockfishEngine = StockfishEngine;

function move_to_uci(move) {
    let uci = move.from + move.to;
    if (move.promotion) {
        uci += move.promotion;
    }
    return uci;
}
window.move_to_uci = move_to_uci;

function score_to_probs(score) {
    let value = 0;
    if (!score.value || !Number.isFinite(score.value)) {
        value = 0;
    } else if (score.type === 'cp') {
        value = score.value;
    } else if (score.type === 'mate') {
        value = score.value > 0 ? 100000 : -100000;
    }

    const exp = Math.exp(-value / 400.0);
    const probWhite = 1 / (1 + exp);
    const probBlack = exp / (1 + exp);
    return [probWhite, probBlack];
}
window.score_to_probs = score_to_probs;
