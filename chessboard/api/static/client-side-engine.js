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

    let lastAnalyzeInfo = null;
    let currentAnalyzeFen = null;

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
                lastAnalyzeInfo = info;

                // Stream a snapshot to the callback (not the mutable reference)
                current.callback && current.callback({
                    info,
                    bestmove: null,
                    done: false,
                    fen: currentAnalyzeFen,
                });

                if (info.multipv === 1) {
                    current.lastInfo = info;
                }
            }
        }
        else if (text.startsWith('bestmove')) {
            const parts = text.split(/\s+/);
            const move = parts[1] || '-';
            const ponder = parts[3] || null;

            if (current) {
                // Final snapshot result
                const finalResult = {
                    info: lastAnalyzeInfo ? { ...lastAnalyzeInfo } : null,
                    bestmove: {
                        move: move,
                        ponder: ponder,
                        raw: text
                    },
                    done: true,
                    fen: currentAnalyzeFen,
                };

                cache[finalResult.fen] = finalResult;

                current.resolve(finalResult);
                current.callback && current.callback(finalResult);
                current = null;

                // Reset internal mutable holder
                lastAnalyzeInfo = null;
                currentAnalyzeFen = null;
            }
        }
    };

    // Initial handshake
    post('uci');
    post('isready');

    async function ready() { await readyPromise; }

    async function analyze({ fen, depth = 32, callback = () => { } } = {}) {
        if (typeof fen !== 'string' || fen.length === 0) {
            throw new Error('analyze() requires a FEN or "startpos"');
        }

        // Short-circuit on cache hit: invoke callback with a snapshot and return a snapshot
        if (fen in cache) {
            const cached = cache[fen];
            const snapshot = {
                info: cached.info ? { ...cached.info } : null,
                bestmove: { ...cached.bestmove },
                done: cached.done,
                fen: cached.fen,
            };
            callback(snapshot);
            return Promise.resolve(snapshot);
        }

        // Cancel any previous analysis
        if (current) {
            try { post('stop'); } catch (_) { }
            current = null;
        }
        await ready();
        // New game + position
        post('ucinewgame');
        post('isready');
        await ready(); // wait again to ensure options reset

        currentAnalyzeFen = fen;

        if (fen === 'startpos') {
            post('position startpos');
        } else {
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
        return p; // always resolves with the final snapshot result
    }

    async function analyzeMove({ fenBeforeMove, move, depth = 32, blunderThreshold = 0.5, callback } = {}) {

        const chess = new Chess(fenBeforeMove);
        const turn = chess.turn();

        const starting_fen = chess.fen();
        const move_san = chess.move(move, { sloppy: true })?.san;
        if (move_san === null) {
            throw new Error('Invalid move: ' + move + ' fen: ' + fenBeforeMove);
        }
        const new_fen = chess.fen();

        // Analyze starting position
        const start_fen_result = await analyze({
            fen: starting_fen,
            depth: depth,
            callback: () => { } // No-op or handle info updates if needed
        });

        chess.undo();
        const best_move_san = chess.move(start_fen_result.bestmove.move, { sloppy: true }).san;
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

        if (!start_fen_result.info || !end_fen_result.info || !best_move_result.info) {
            throw new Error('Failed to get complete analysis info for move: ' + move_san);
        }
        if (best_move_result.info.score.type !== 'cp' || end_fen_result.info.score.type !== 'cp' || start_fen_result.info.score.type !== 'cp') {
            throw new Error('Invalid score type in analysis info for move: ' + move_san + '(got types: ' +
                start_fen_result.info.score.type + ', ' + end_fen_result.info.score.type + ', ' + best_move_result.info.score.type + ')');
        }

        // Convert centipawns to pawns
        const pre_move_score = (start_fen_result.info.score.value / 100);
        const post_move_score = (end_fen_result.info.score.value / 100);
        const best_move_score = (best_move_result.info.score.value / 100);


        const score_diff = post_move_score - pre_move_score;
        const best_move_score_diff = best_move_score - pre_move_score;
        const score_diff_norm = (turn === 'w' ? score_diff : -score_diff);
        const best_move_score_diff_norm = (turn === 'w' ? best_move_score_diff : -best_move_score_diff);

        const is_blunder = score_diff_norm <= -blunderThreshold && best_move_score_diff_norm >= -blunderThreshold;

        return {
            start_result: start_fen_result,
            end_result: end_fen_result,
            best_move_result: best_move_result,
            best_move_fen: best_move_fen,
            start_fen: starting_fen,
            end_fen: new_fen,
            move: move_san,
            best_move: best_move_san,
            score: post_move_score,
            pre_move_score: pre_move_score,
            best_move_score: best_move_score,
            score_diff: score_diff,
            score_diff_norm: score_diff_norm,
            best_move_score_diff: best_move_score_diff,
            best_move_score_diff_norm: best_move_score_diff_norm,
            blunder: is_blunder,
            turn: turn,
        }
    }

    async function analyzePGN({ pgn, depth = 16, onMoveAnalyzed = null } = {}) {
        const chess = new Chess();
        const success = chess.load_pgn(pgn);
        if (!success) {
            throw new Error('Invalid PGN string');
        }
        const moves = chess.history({ verbose: true }).map(m => m.san);
        chess.reset(); // Reset to start position

        const results = [];

        for (const move of moves) {
            const fenBeforeMove = chess.fen();

            // Analyze position before the move
            const analysisResult = await analyzeMove({
                fenBeforeMove: fenBeforeMove,
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