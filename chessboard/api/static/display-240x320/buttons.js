// --- Long press detection for all 4 buttons ---
// Button mapping: Up(2/ArrowUp), Down(3/ArrowDown), Right(4/ArrowRight/Enter), Left(1/ArrowLeft/Backspace/Escape)
const buttonTimers = {};
const LONG_PRESS_DURATION = 300; // ms

buttonDown = [false, false, false, false]; // Track button states

let buttonFunctions = [
    { short: null, shortHint: '', long: null, longHint: '' },
    { short: null, shortHint: '', long: null, longHint: '' },
    { short: null, shortHint: '', long: null, longHint: '' },
    { short: null, shortHint: '', long: null, longHint: '' },
];

function startButtonTimer(buttonIndex) {
    clearButtonTimer(buttonIndex);
    buttonTimers[buttonIndex] = setTimeout(() => {
        if (buttonFunctions[buttonIndex] && buttonFunctions[buttonIndex].long) {
            buttonFunctions[buttonIndex].long();
        }
        else {
            console.warn('No long press function defined for button', buttonIndex + 1);
        }
        buttonTimers[buttonIndex] = null;
    }, LONG_PRESS_DURATION);
}

function clearButtonTimer(buttonIndex) {
    if (buttonTimers[buttonIndex]) {
        clearTimeout(buttonTimers[buttonIndex]);
        buttonTimers[buttonIndex] = null;
    }
}

// Update button hints based on current view
function buttonsUpdate(newButtonFunctions) {
    buttonFunctions = newButtonFunctions;

    for (let i = 0; i < 4; i++) {
        const button = document.getElementById(`hint-${i}`);
        if (button && buttonFunctions[i]) {
            button.textContent = buttonFunctions[i].shortHint;
            if (buttonFunctions[i].long != null) {
                button.textContent += ' / ' + buttonFunctions[i].longHint;
            }
        }

    }
}

function getButtonIndexFromKey(key) {
    switch (key) {
        case '1':
        case 'ArrowLeft':
            return 0;
        case '2':
        case 'ArrowUp':
            return 1;
        case '3':
        case 'ArrowDown':
            return 2;
        case '4':
        case 'ArrowRight':
            return 3;
        default:
            return null;
    }
}

document.addEventListener('keydown', function (e) {
    // Prevent repeat firing
    if (e.repeat) return;

    key = getKey(e);
    let index = getButtonIndexFromKey(key);
    if ((index === null) || buttonDown[index]) {
        return;
    }

    buttonDown[index] = true;

    startButtonTimer(index);
});

document.addEventListener('keyup', function (e) {
    key = getKey(e);
    let index = getButtonIndexFromKey(key);

    if (index != null) {
        if (buttonTimers[index]) {
            // Timer still running: treat as short press
            clearButtonTimer(index);
            if (buttonFunctions[index] && buttonFunctions[index].short) {
                buttonFunctions[index].short();
            }
        }
        buttonDown[index] = false;
    }
});