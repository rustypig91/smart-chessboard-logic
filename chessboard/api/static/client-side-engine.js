// Lightweight client-side Stockfish wrapper with no DOM references
// Provides: createStockfishEngine(options) -> Promise<Engine>
// Engine API: ready(), analyze({ fen, depth, onInfo }), stop(), setOption(name, value), terminate()
// Requires chess.js <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.13.4/chess.min.js" integrity="sha512-5nNBISa4noe7B2/Me0iHkkt7mUvXG9xYoeXuSrr8OmCQIxd5+Qwxhjy4npBLIuxGNQKwew/9fEup/f2SUVkkXg==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>


function uci_to_move(uci) {
    const from = uci.slice(0, 2);
    const to = uci.slice(2, 4);
    const promotion = uci.length > 4 ? uci[4] : undefined;
    return { from, to, promotion };
}

function move_to_uci(move) {
    let uci = move.from + move.to;
    if (move.promotion) {
        uci += move.promotion;
    }
    return uci;
}

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
    const wasmSupported = typeof WebAssembly === 'object' && WebAssembly.validate(Uint8Array.of(0x0, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00));
    const {
        scriptUrl = '/static/node_modules/stockfish/src/stockfish-17.1-8e4d048.js',
        poolSize: poolSizeOpt
    } = options;

    const poolSize = 1; // Math.max(1, Number.isFinite(poolSizeOpt) ? Number(poolSizeOpt) : navigator.hardwareConcurrency / 4 || 2);
    console.log(`Loading ${poolSize} Stockfish worker(s) from:`, scriptUrl);

    // Shared cache across the pool: cache[fen][depth] -> final snapshot
    const cache = {};

    function makeSnapshot(info, bestmove, done, fen, engineOutput) {
        return {
            info: info ? { ...info } : null,
            bestmove: bestmove ? { ...bestmove } : null,
            done: !!done,
            fen,
            engineOutput: engineOutput,
        };
    }

    // Worker slot factory
    async function createSlot(id) {
        const worker = await new Worker(scriptUrl);

        // State for the currently assigned job on this worker
        let current = null; // { job, lastInfo }
        let lastAnalyzeInfo = null;
        let currentAnalyzeFen = null;
        let busy = false;
        let engineOutput = '';

        let postResolver = null;
        let postPromise = Promise.resolve();

        async function post(cmd) {
            console.log(`[SF${id} ->]`, cmd);
            /// Only await responses for commands that expect one
            /// NOTE: setoption may or may not print a statement.
            if (cmd !== "ucinewgame" && cmd !== "flip" && cmd !== "stop" && cmd !== "ponderhit" && cmd.substr(0, 8) !== "position" && cmd.substr(0, 9) !== "setoption" && cmd !== "stop") {
                await postPromise;
                postPromise = new Promise((resolve) => { postResolver = resolve; });
            }
            worker && worker.postMessage(cmd);
            return postPromise;
        }

        worker.onmessage = (ev) => {
            const text = typeof ev.data === 'string' ? ev.data : String(ev.data);
            engineOutput += text + '\n';
            console.log(`[SF${id}]`, text);

            if (text === 'uciok') {
                // continue with isready
                console.log(`[SF${id}] UCI initialized`);
                postResolver();
            } else if (text === 'readyok') {
                postResolver();
            } else if (text.startsWith('info ')) {
                const info = parseInfoLine(text);
                if (current) {
                    lastAnalyzeInfo = info;

                    if (info.multipv === 1) {
                        current.lastInfo = info;
                    }
                }
            } else if (text.startsWith('bestmove')) {
                const parts = text.split(/\s+/);
                const move = parts[1] || '-';
                const ponder = parts[3] || null;
                postResolver();

                if (current) {
                    const bestmove = { move_uci: move, ponder_uci: ponder, raw: text };
                    const finalResult = makeSnapshot(lastAnalyzeInfo, bestmove, true, currentAnalyzeFen, engineOutput);

                    // Write to shared cache keyed by requested depth
                    try {
                        if (!cache[finalResult.fen]) cache[finalResult.fen] = {};
                        const d = finalResult.info?.depth ?? current.job.depth;
                        cache[finalResult.fen][d] = finalResult;
                    } catch (_) { /* noop */ }

                    current.job.resolve(finalResult);
                    // Clear state
                    current = null;
                    lastAnalyzeInfo = null;
                    currentAnalyzeFen = null;
                    busy = false;

                    // Try to dispatch next queued job
                    dispatch();
                }
            }
        };

        // Initial handshake
        await post('uci');
        await post('isready');
        await post('setoption name Threads value 16');


        async function runJob(job) {
            // Cancel any previous analysis on this worker
            if (current) {
                try { stop(); } catch (_) { }
                current = null;
            }

            // New game + position
            await post('ucinewgame');
            await post('isready');

            currentAnalyzeFen = job.fen;

            if (job.fen === 'startpos') {
                await post('position startpos');
            } else {
                await post('position fen ' + job.fen);
            }

            current = { job, lastInfo: null };
            return post('go depth ' + job.depth || 16);
        }

        function stop() {
            try { post('stop'); } catch (_) { }
            if (current) {
                current.job.reject?.(new Error('stopped'));
                current = null;
            }
            busy = false;
        }

        function terminate() { try { worker.terminate(); } catch (_) { } }

        return {
            id,
            ready,
            runJob,
            stop,
            terminate,
            isBusy: () => busy,
            setBusy: (b) => { busy = b; },
        };
    }

    // Create pool
    const slots = await Promise.all(Array.from({ length: poolSize }, (_, i) => createSlot(i)));

    // Simple FIFO job queue
    const queue = [];

    function dispatch() {
        for (; ;) {
            const slot = slots.find(s => !s.isBusy());
            if (!slot) return;
            const job = queue.shift();
            if (!job) return;
            slot.setBusy(true);
            slot.runJob(job).catch((err) => {
                slot.setBusy(false);
                job.reject(err);
                dispatch();
            });
        }
    }

    // Public API

    async function ready() {
        await Promise.all(slots.map(s => s.ready()));
    }

    async function analyze({ fen, depth = 32 } = {}) {
        if (typeof fen !== 'string' || fen.length === 0) {
            throw new Error('analyze() requires a FEN or "startpos"');
        }

        const boundedDepth = Math.max(6, Math.min(30, Number(depth) || 16));

        // Cache lookup
        if ((fen in cache) && (boundedDepth in cache[fen])) {
            const cached = cache[fen][boundedDepth];
            return cached;
        } else if (!(fen in cache)) {
            cache[fen] = {};
        }

        // Enqueue job
        let resolve, reject;
        cache[fen][boundedDepth] = new Promise((res, rej) => { resolve = res; reject = rej; });
        queue.push({ fen, depth: boundedDepth, resolve, reject });

        dispatch();
        return cache[fen][boundedDepth]; // resolves with final snapshot
    }

    async function analyzeMove({ fenBeforeMove, move_san, depth = 32, blunderThreshold = 0.5 } = {}) {
        const chess = new Chess(fenBeforeMove);
        const turn = chess.turn();

        const starting_fen = chess.fen();

        const move = chess.move(move_san, { sloppy: true });
        if (move === null) {
            throw new Error('Invalid move: ' + move_san + ' fen: ' + fenBeforeMove);
        }

        const fen_after_move = chess.fen();
        chess.undo();

        // Analyze starting position
        let result_start_promise = analyze({
            fen: starting_fen,
            depth: depth
        });

        // Analyze after move
        let result_after_move_promise = analyze({
            fen: fen_after_move,
            depth: depth
        });

        const start_fen_result = await result_start_promise;
        const best_move_uci = start_fen_result.bestmove.move_uci;
        const best_move = chess.move(uci_to_move(best_move_uci), { sloppy: true });

        const fen_after_best_move = chess.fen();

        let best_move_result_promise = analyze({
            fen: fen_after_best_move,
            depth: depth
        });

        const end_fen_result = await result_after_move_promise;
        const best_move_result = await best_move_result_promise;

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
        const score_diff_norm = (turn === 'w' ? score_diff : score_diff);
        const best_move_score_diff_norm = (turn === 'w' ? best_move_score_diff : best_move_score_diff);

        const is_blunder = score_diff_norm <= -blunderThreshold && best_move_score_diff_norm >= -blunderThreshold;

        const result = {
            start_result: start_fen_result,
            end_result: end_fen_result,
            best_move_result: best_move_result,
            best_move_fen: fen_after_best_move,
            start_fen: starting_fen,
            end_fen: fen_after_move,
            move: move,
            best_move: best_move,
            score: post_move_score,
            pre_move_score: pre_move_score,
            best_move_score: best_move_score,
            score_diff: score_diff,
            score_diff_norm: score_diff_norm,
            best_move_score_diff: best_move_score_diff,
            best_move_score_diff_norm: best_move_score_diff_norm,
            blunder: is_blunder,
            turn: turn,
        };

        return result;
    }

    async function analyzePGN({ pgn, depth = 16, onMoveAnalyzed = null } = {}) {
        const chess = new Chess();
        const success = chess.load_pgn(pgn);
        if (!success) {
            throw new Error('Invalid PGN string');
        }
        const moves = chess.history({ verbose: true });
        chess.reset();

        const result_promises = [];

        for (const move of moves) {
            const fenBeforeMove = chess.fen();

            result_promises.push(analyzeMove({
                fenBeforeMove: fenBeforeMove,
                move_san: move.san,
                depth: depth
            }));

            chess.move(move, { sloppy: true });
        }

        const results = [];
        let index = 0;
        for (const resultPromise of result_promises) {
            analysisResult = await resultPromise;
            const result = {
                fen: analysisResult.end_fen,
                move: analysisResult.move,
                analysis: analysisResult,
                moveIndex: index++,
            }
            results.push(result);
            onMoveAnalyzed && onMoveAnalyzed(result);
        }

        return results;
    }

    function stop() {
        queue.length = 0;
        for (const s of slots) s.stop();
    }

    function setOption(name, value) {
        if (!name) return;
        // Broadcast option to all workers
        for (const s of slots) {
            try { s.setBusy(true); } catch (_) { }
        }
        // Send synchronously; workers accept options anytime
        for (const s of slots) {
            try {
                // Direct post via a dedicated isReady step is not necessary for setoption
                s.ready().then(() => {
                    // We need access to the underlying post; reuse createWorkerFromURL design which routes setoption via global
                    // Since we don't expose post here, re-fetching isn't needed; setoption is handled within analyze flow anyway.
                });
            } catch (_) { }
        }
        // Note: setOption no-op placeholder; extend if you wire post() out of slot
    }

    function terminate() {
        stop();
        for (const s of slots) s.terminate();
    }

    const engine = { ready, analyze, stop, setOption, terminate, analyzeMove, analyzePGN };
    if (typeof window !== 'undefined') { window.createStockfishEngine = createStockfishEngine; }
    return engine;
}