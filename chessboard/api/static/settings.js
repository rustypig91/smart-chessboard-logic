
function getSettings(callback) {
    fetch('/api/settings')
        .then(response => response.json())
        .then(data => {
            callback(data);
        });

}

function settingGet(key, callback) {
    fetch(`/api/settings/${encodeURIComponent(key)}`)
        .then(response => response.json())
        .then(data => {
            callback(data);
        });
}


function settingSet(key, value, callback) {
    fetch(`/api/settings/${encodeURIComponent(key)}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ value: value })
    })
        .then(response => response.json())
        .then(data => {
            if (callback) {
                callback(data);
            }
        });
}