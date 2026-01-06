/**
    * Fetch function for Qt5 using XMLHttpRequest.
    * Usage: fetchQt5(url, options).then(response => ...).catch(error => ...);
    */
function fetchQt5(url, options = {}) {
    return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open(options.method || 'GET', url, true);

        // Set headers if provided
        if (options.headers) {
            for (var key in options.headers) {
                xhr.setRequestHeader(key, options.headers[key]);
            }
        }

        xhr.onreadystatechange = function () {
            if (xhr.readyState === 4) {
                var response = {
                    ok: xhr.status >= 200 && xhr.status < 300,
                    status: xhr.status,
                    statusText: xhr.statusText,
                    text: function () { return Promise.resolve(xhr.responseText); },
                    json: function () {
                        try {
                            return Promise.resolve(JSON.parse(xhr.responseText));
                        } catch (e) {
                            return Promise.reject(e);
                        }
                    }
                };
                if (response.ok) {
                    resolve(response);
                } else {
                    reject(response);
                }
            }
        };

        xhr.onerror = function () {
            reject(new Error('Network error'));
        };

        xhr.send(options.body || null);
    });
}

if (typeof fetch === 'undefined') {
    window.fetch = fetchQt5;
}

// Key event listener compatibility for Qt5
function getKey(e) {
    if (e.key) {
        // Modern browsers
        return e.key;
    }
    // Older browsers/Qt5
    switch (e.keyCode || e.which) {
        case 37: return 'ArrowLeft';
        case 38: return 'ArrowUp';
        case 39: return 'ArrowRight';
        case 40: return 'ArrowDown';
        case 13: return 'Enter';
        case 27: return 'Escape';
        case 8: return 'Backspace';
        default: return String.fromCharCode(e.keyCode || e.which);
    }
}

function padStart(str, targetLength, padString) {
    str = String(str);
    while (str.length < targetLength) {
        str = padString + str;
    }
    return str;
}

// Polyfill for Object.entries for older JS environments
if (!Object.entries) {
    Object.entries = function (obj) {
        var ownProps = Object.keys(obj), i = ownProps.length, resArray = new Array(i);
        while (i--)
            resArray[i] = [ownProps[i], obj[ownProps[i]]];
        return resArray;
    };
}
