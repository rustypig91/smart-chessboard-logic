// Make sure the Socket.IO client library is loaded in your HTML before this script:
// <script src="/socket.io/socket.io.js"></script>
// Place this script tag after the Socket.IO script tag in your HTML to ensure 'io' is defined.
socket = io();

function sendEvent(eventType, eventData = {}) {
    console.log("Sending event:", eventType, eventData);
    socket.emit("publish_event", {
        event_type: eventType,
        event_data: eventData,
    });
}

function addBoardEventListener(eventType, callback) {
    socket.on("board_event." + eventType, callback);
    socket.emit("subscribe", {
        event_type: eventType
    });
}

function removeBoardEventListener(eventType, callback) {
    socket.off("board_event." + eventType, callback);
    socket.emit("unsubscribe", {
        event_type: eventType
    });
}

// if (!window._socketOnAnySet) {
//     window.socket.onAny((event, ...args) => {
//         if (event === "board_event.SetSquareColorEvent") return; // Disabled to not spam the console
//         if (event == "board_event.HalSensorVoltageEvent") return;

//         console.log("Socket.IO event:", event, args);
//     });
//     window._socketOnAnySet = true;
// }
