// Lightweight client-side Stockfish wrapper with no DOM references
// Provides: createStockfishEngine(options) -> Promise<Engine>
// Engine API: ready(), analyze({ fen, depth, onInfo }), stop(), setOption(name, value), terminate()
// Requires chess.js <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.13.4/chess.min.js" integrity="sha512-5nNBISa4noe7B2/Me0iHkkt7mUvXG9xYoeXuSrr8OmCQIxd5+Qwxhjy4npBLIuxGNQKwew/9fEup/f2SUVkkXg==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>

const DEFAULT_STOCKFISH_JS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js';
const DEFAULT_STOCKFISH_WASM_JS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.wasm.js';
const DEFAULT_STOCKFISH_WASM_BIN_URL = 'https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.wasm';

async function createWorkerFromURL(url, wasmBinUrl) {
    const res = await fetch(url, { mode: 'cors' });
    let code = await res.text();

    code = code.replace(/stockfish\.wasm/g, wasmBinUrl);

    const blob = new Blob([code], { type: 'application/javascript' });
    return new Worker(URL.createObjectURL(blob));
}

function parseInfoLine(text) {
    // Parse an 'info' line from Stockfish into a structured object
    // Example: info depth 20 seldepth 33 multipv 1 score cp 13 nodes 123456 nps 12345 time 100 pv e2e4 e7e5 ...
    const tokens = text.trim().split(/\s+/);
    const getNum = (key) => {
        const i = tokens.indexOf(key);
        if (i >= 0 && i + 1 < tokens.length) {
            const n = Number(tokens[i + 1]);
            return Number.isFinite(n) ? n : undefined;
        }
        return undefined;
    };

    const depth = getNum('depth');
    const seldepth = getNum('seldepth');
    const multipv = getNum('multipv') ?? 1;
    const nodes = getNum('nodes');
    const nps = getNum('nps');
    const time = getNum('time');

    let score = undefined;
    const si = tokens.indexOf('score');
    if (si >= 0 && si + 2 < tokens.length) {
        const type = tokens[si + 1];
        const valRaw = tokens[si + 2];
        if (type === 'cp') {
            const cp = Number(valRaw);
            if (Number.isFinite(cp)) score = { type: 'cp', value: cp };
        } else if (type === 'mate') {
            const m = Number(valRaw);
            if (Number.isFinite(m)) score = { type: 'mate', value: m };
        }
    }

    let pv = [];
    const pvi = tokens.indexOf('pv');
    if (pvi >= 0 && pvi + 1 < tokens.length) {
        pv = tokens.slice(pvi + 1);
    }

    return { depth, seldepth, multipv, nodes, nps, time, score, pv, raw: text };
}

async function createStockfishEngine(options = {}) {
    var wasmSupported = typeof WebAssembly === 'object' && WebAssembly.validate(Uint8Array.of(0x0, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00));
    console.log('WebAssembly supported:', wasmSupported);

    const { scriptUrl = wasmSupported ? DEFAULT_STOCKFISH_WASM_JS_URL : DEFAULT_STOCKFISH_JS_URL } = options;
    console.log('Loading Stockfish from:', scriptUrl);

    // Redirect wasm binary fetch to CDN to work within blob worker
    const worker = await createWorkerFromURL(scriptUrl, wasmSupported ? DEFAULT_STOCKFISH_WASM_BIN_URL : undefined);

    let readyResolver = null;
    const readyPromise = new Promise((resolve) => { readyResolver = resolve; });
    let current = null; // { resolve, reject, onInfo, lastInfo }

    function post(cmd) { worker && worker.postMessage(cmd); }

    let lastAnalyzeResult = {
        info: null,
        bestmove: {
            move: null,
            ponder: null,
            raw: null,
        },
        done: false,
        fen: null,
    }

    let cache = {};

    worker.onmessage = (ev) => {
        const text = typeof ev.data === 'string' ? ev.data : String(ev.data);
        if (text === 'uciok') {
            // continue with isready
        }
        else if (text === 'readyok') {
            if (readyResolver) {
                readyResolver();
                readyResolver = null;
            }
        }
        else if (text.startsWith('info ')) {
            const info = parseInfoLine(text);
            // Prefer multipv 1 for display/aggregation
            if (current) {
                lastAnalyzeResult.info = info;

                current.callback(lastAnalyzeResult);

                if (info.multipv === 1) {
                    current.lastInfo = info;
                }
            }
        }
        else if (text.startsWith('bestmove')) {
            const parts = text.split(/\s+/);
            const move = parts[1] || '-';
            const ponder = parts[3] || null;

            lastAnalyzeResult.bestmove.move = move;
            lastAnalyzeResult.bestmove.ponder = ponder;
            lastAnalyzeResult.bestmove.raw = text;
            lastAnalyzeResult.done = true;

            if (current) {
                cache[lastAnalyzeResult.fen] = { ...lastAnalyzeResult };
                cache[lastAnalyzeResult.fen].bestmove = { ...lastAnalyzeResult.bestmove };
                cache[lastAnalyzeResult.fen].info = { ...lastAnalyzeResult.info };

                current.resolve(lastAnalyzeResult);
                current.callback(lastAnalyzeResult);
                current = null;

                lastAnalyzeResult.info = null;
                lastAnalyzeResult.bestmove.move = null;
                lastAnalyzeResult.bestmove.ponder = null;
                lastAnalyzeResult.bestmove.raw = null;
                lastAnalyzeResult.done = false;
                lastAnalyzeResult.fen = null;
            }
        }
    };

    // Initial handshake
    post('uci');
    post('isready');

    async function ready() { await readyPromise; }

    async function analyze({ fen, depth = 32, callback } = {}) {
        if (!callback) {
            return;
        }

        if (typeof fen !== 'string' || fen.length === 0) {
            throw new Error('analyze() requires a FEN or "startpos"');
        }

        console.warn('Cache is: ', cache);
        if (fen in cache) {
            callback(cache[fen]);
            return Promise.resolve(cache[fen]);
        } else {
            console.error('Cache miss for fen:', fen);
        }

        console.log('analyze called with', fen, depth);

        if (!fen || typeof fen !== 'string') {
            throw new Error('analyze() requires a FEN or "startpos"');
        }

        // Cancel any previous analysis
        if (current) {
            try {
                post('stop');
            } catch (_) { }
            current = null;
        }
        await ready();
        // New game + position
        post('ucinewgame');
        post('isready');
        await ready(); // wait again to ensure options reset

        lastAnalyzeResult.fen = fen;

        if (fen === 'startpos') {
            post('position startpos');
        }
        else {
            post('position fen ' + fen);
        }

        current = {
            resolve: null,
            reject: null,
            callback,
            lastInfo: null,
        };

        const p = new Promise((resolve, reject) => { current.resolve = resolve; current.reject = reject; });

        post('go depth ' + Math.max(6, Math.min(30, Number(depth) || 16)));
        return p;
    }

    async function analyzeMove({ fen, move, depth = 32, callback } = {}) {

        const chess = new Chess(fen);

        const starting_fen = chess.fen();
        const moveResult = chess.move(move, { sloppy: true });
        if (moveResult === null) {
            throw new Error('Invalid move: ' + move + ' fen: ' + fen);
        }
        const new_fen = chess.fen();

        // Analyze starting position
        const start_fen_result = await analyze({
            fen: starting_fen,
            depth: depth,
            callback: () => { } // No-op or handle info updates if needed
        });

        chess.undo();
        chess.move(start_fen_result.bestmove.move, { sloppy: true });
        const best_move_fen = chess.fen();

        // Analyze after move
        const end_fen_result = await analyze({
            fen: new_fen,
            depth: depth,
            callback: () => { }
        });

        const best_move_result = await analyze({
            fen: best_move_fen,
            depth: depth,
            callback: () => { }
        });

        return {
            start_result: start_fen_result,
            end_result: end_fen_result,
            best_move_result: best_move_result,
            best_move_fen: best_move_fen,
            start_fen: starting_fen,
            end_fen: new_fen,
            move: move,
            best_move: moveResult,
            move_san: moveResult.san,
            score_diff: end_fen_result.info && start_fen_result.info ? {
                type: end_fen_result.info.score.type,
                value: end_fen_result.info.score.value - start_fen_result.info.score.value
            } : null,
            best_move_score_diff: best_move_result.info && end_fen_result.info ? {
                type: best_move_result.info.score.type,
                value: best_move_result.info.score.value - end_fen_result.info.score.value
            } : null,
            blunder: end_fen_result.info && start_fen_result.info && best_move_result.info ? (
                (start_fen_result.info.score.type === 'cp' && end_fen_result.info.score.type === 'cp' && best_move_result.info.score.type === 'cp') ?
                    (start_fen_result.info.score.value - end_fen_result.info.score.value >= 100 &&
                        best_move_result.info.score.value - end_fen_result.info.score.value >= 100)
                    : false
            ) : false,
        }
    }


    async function analyzePGN({ pgn, depth = 16, onMoveAnalyzed = null } = {}) {
        const chess = new Chess();
        console.log('Parsing PGN:', pgn);
        const success = chess.load_pgn(pgn);
        if (!success) {
            throw new Error('Invalid PGN string');
        }
        const moves = chess.history({ verbose: true }).map(m => m.san);
        chess.reset(); // Reset to start position

        const results = [];

        for (const move of moves) {
            console.log('PGN Move:', move);
            const fenBeforeMove = chess.fen();

            // Analyze position before the move
            const analysisResult = await analyzeMove({
                fen: fenBeforeMove,
                move: move,
                depth: depth,
                callback: () => { }
            });

            console.log('Analyzed move:', move, 'Result:', analysisResult);

            results.push({
                move: move,
                fen: fenBeforeMove,
                analysis: analysisResult
            });

            if (onMoveAnalyzed) {
                onMoveAnalyzed({
                    move: move,
                    fen: fenBeforeMove,
                    analysis: analysisResult
                });
            }

            // Make the move on the board
            chess.move(move, { sloppy: true });
        }

        return results;
    }

    function stop() { post('stop'); if (current) { current.reject?.(new Error('stopped')); current = null; } }

    function setOption(name, value) { if (!name) return; post(`setoption name ${name} value ${value}`); }

    function terminate() { try { worker.terminate(); } catch (_) { } }

    const engine = { ready, analyze, stop, setOption, terminate, analyzeMove, analyzePGN };
    if (typeof window !== 'undefined') { window.createStockfishEngine = createStockfishEngine; }
    return engine;
}