export class StockfishEngine {
    constructor(options = {}) {
        this.workerUrl = options.workerUrl || '/static/node_modules/stockfish/src/stockfish-17.1-8e4d048.js';
        this.numThreads = options.numThreads || navigator.hardwareConcurrency || 4;
        this.worker = new Worker(this.workerUrl);

        this.queue = new AsyncQueue();

        // this.worker.addEventListener('message', (event) => {
        //     console.log('Stockfish message:', event.data);
        // });

        this.readyPromise = new Promise(async (resolve) => {
            await this._postMessage('uci', 'uciok', null, null);
            await this._postMessage('isready', 'readyok', null, null);
            await this._postMessage(`setoption name Threads value ${this.numThreads}`);
            console.log(`Stockfish engine ready and initialized with ${this.numThreads} threads.`);
            resolve();
        });

        this.analyzeCache = {};
    }

    async _postMessageToQueue(message, response = '', lineCallback = null, doneCallback = null) {
        await this.readyPromise;
        return this.queue.enqueue(() => this._postMessage(message, response, lineCallback, doneCallback)).catch((err) => {
            console.error(`Error in _postMessageToQueue(${message}): ${err}`);
        });
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
        try {
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
            }).catch((err) => {
                console.error('Error in _postMessage promise:', err);
            });
        } catch (err) {
            console.error('Error in _postMessage:', err);
        }
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
        await self.readyPromise;

        const uciMoves = moves.map(move => {
            if (typeof move === 'string') {
                return move;
            }
            return move_to_uci(move)
        });
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

    async _stop() {
        await self.readyPromise;
        return this._postMessage('stop');
    }

    async stop() {
        await self.readyPromise;
        this._postMessage('stop');
        return this.queue.clear();

    }

    async analyzePosition(startpos = "startpos", moves = [], depth = 32, infoCallback = null) {
        await this.readyPromise;
        console.log('Moves:', moves);
        let cacheHash = `${startpos}${moves.map(move => move.san).join('')}${depth}`;
        let cacheHit = this.analyzeCache[cacheHash];
        if (cacheHit) {
            if (cacheHit.latestInfo && infoCallback) {
                infoCallback(cacheHit.latestInfo);
            }
            if (infoCallback && cacheHit.callbacks != null) {
                this.analyzeCache[cacheHash].callbacks.push(infoCallback);
            }
            return this.analyzeCache[cacheHash].promise;
        }

        let resolve, reject;
        let promise = new Promise((res, rej) => {
            resolve = res;
            reject = rej;
        });

        let job = { callbacks: infoCallback ? [infoCallback] : [], promise: promise, latestInfo: null };
        this.analyzeCache[cacheHash] = job;

        this.queue.enqueue(async () => {
            console.log(`Analyzing position: ${startpos} with ${moves.length} moves to depth ${depth}`);
            await this._stop();
            await this._position(startpos, moves);

            return this._postMessage(`go depth ${depth}`, 'bestmove', (infoResponse) => {
                if (infoResponse.startsWith('info depth ')) {
                    job.latestInfo = new Info(infoResponse, fenFromMoves(moves, startpos));
                    for (const callback of job.callbacks) {
                        callback(job.latestInfo);
                    }
                }
            }, (bestmoveResponse) => {
                if (job.latestInfo && (job.latestInfo.depth == depth || job.latestInfo.score.type === 'mate')) {
                    // Cache the result
                    job.callbacks = null;
                    job.latestInfo.final = true;
                    resolve(job.latestInfo);
                }
                else {
                    this.analyzeCache[cacheHash] = null; // Invalidate cache since we didn't reach desired depth
                    reject(`Analysis did not reach desired depth(${depth}): ${job.latestInfo ? job.latestInfo.depth : 'unknown'}`);
                }
            });
        });

        return job.promise;
    }

    async _startNewGame() {
        await this._postMessage('ucinewgame');
        return this._postMessage('isready', 'readyok');
    }

    async startNewGame() {
        return this.queue.enqueue(async () => {
            return this._startNewGame();
        });
    }

    async analyzePgnGame(pgnText, depth = 32, analysisCallback) {
        let chess = new Chess();
        chess.load_pgn(pgnText);
        const moves = chess.history({ verbose: true });

        this.startNewGame();

        let promises = [];

        for (let i = 0; i <= moves.length; i++) {
            let currentMoves = moves.slice(0, i);
            let lastMove = i > 0 ? currentMoves[i - 1] : null;
            await this.analyzePosition(
                "startpos",
                currentMoves,
                depth,
                (info) => {
                    analysisCallback({
                        moveIndex: i,
                        info: info,
                        moves: currentMoves,
                        fen: info.fen,
                        lastMove: lastMove,
                    });
                });
        }

        return Promise.all(promises);
    }
}

function fenFromMoves(moves, startfen = null) {
    let chess = new Chess();
    if (startfen && startfen !== 'startpos') {
        chess.load(startfen);
    }
    for (const move of moves) {
        chess.move(move);
    }
    return chess.fen();
}

function resolveTurn(fen) {
    if (!fen) {
        console.error('resolveTurn called with empty FEN');
        return 'w';
    }
    const parts = fen.split(' ');
    if (parts.length > 1 && (parts[1] === 'w' || parts[1] === 'b')) {
        return parts[1];
    }

    // Default: assume White
    return 'w';
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
    constructor(text, fen) {
        // Parse an 'info' line from Stockfish into a structured object
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

        this.final = false;
        this.depth = getNum('depth');
        this.seldepth = getNum('seldepth');
        this.multipv = getNum('multipv') ?? 1;
        this.nodes = getNum('nodes');
        this.nps = getNum('nps');
        this.time = getNum('time');
        this.fen = fen;

        // Raw score as reported by Stockfish (from side-to-move perspective)
        this.povScore = { type: null, value: null };
        const si = tokens.indexOf('score');
        if (si >= 0 && si + 2 < tokens.length) {
            const type = tokens[si + 1];
            const valRaw = tokens[si + 2];
            const value = Number(valRaw);
            if (Number.isFinite(value)) {
                if (type === 'mate') {
                    this.povScore = { type: 'mate', value: value };
                } else if (type === 'cp') {
                    this.povScore = { type: 'cp', value: value };
                }
            }
        }
        this.turn = resolveTurn(this.fen);
        this.score = { type: null, value: null };
        this.score.type = this.povScore.type;
        this.score.value = this.turn === 'b' && this.povScore.value !== null
            ? -this.povScore.value
            : this.povScore.value;


        // Principal variation
        this.pv = [];
        const pvi = tokens.indexOf('pv');
        if (pvi >= 0 && pvi + 1 < tokens.length) {
            this.pv = tokens.slice(pvi + 1);
        }
        [this.winProbabilityWhite, this.winProbabilityBlack] = this._getScoreProbability();
    }

    _getScoreProbability() {
        let value = 0;
        if (this.score.value == null || !Number.isFinite(this.score.value)) {
            console.warn('Info: Invalid score value for probability calculation:', this.score);
            value = 0;
        } else if (this.score.type === 'cp') {
            value = this.score.value;
        } else if (this.score.type === 'mate') {
            value = this.score.value > 0 ? 100000 : -100000;
            if (this.score.value == 0) {
                value = this.turn === 'w' ? -100000 : 100000;
            }
        }

        const exp = Math.exp(-value / 400.0);
        const probWhite = 1 / (1 + exp);
        const probBlack = exp / (1 + exp);
        return [probWhite, probBlack];
    }
};


class AsyncQueue {
    constructor() {
        this.queue = [];
        this.running = false;
        this.clearRequested = false;

        this.clearResolve = null;
    }

    async enqueue(asyncFn) {
        return new Promise((resolve, reject) => {
            this.queue.push({ asyncFn, resolve, reject });
            this.run();
        });
    }

    async clear() {
        console.warn('AsyncQueue: Clear requested');
        return new Promise((resolve) => {
            this.clearRequested = true;
            this.clearResolve = resolve;
            if (!this.running) {
                resolve();
                this.clearRequested = false;
                this.clearResolve = null;
            }
        });
    }

    async run() {
        if (this.running) return;
        this.running = true;

        while (this.queue.length) {
            const { asyncFn, resolve, reject } = this.queue.shift();
            if (this.clearRequested) {
                reject(`AsyncQueue cleared: ${asyncFn}`);
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
        if (this.clearResolve) {
            this.clearResolve();
        }
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

function uci_to_move(uci) {
    let move = {
        from: uci.slice(0, 2),
        to: uci.slice(2, 4),
    };
    if (uci.length > 4) {
        move.promotion = uci[4];
    }
    return move;
}
window.uci_to_move = uci_to_move;

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
