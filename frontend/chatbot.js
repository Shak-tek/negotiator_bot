const chatInput = document.querySelector(".input-field input");
const sendChatBtn = document.querySelector(".input-field button");
const chatbox = document.querySelector(".box");
const dealButtons = document.getElementById("deal-buttons");  // Get the deal buttons div
const dealBtn = document.getElementById("deal-btn");
const noDealBtn = document.getElementById("no-deal-btn");

sendChatBtn.addEventListener("click", () => {
    let userMessage = chatInput.value.trim();

    if (userMessage) {
        appendMessage("user", userMessage);
        sendToBackend(userMessage);
        chatInput.value = "";
        chatInput.focus();
    }
});

chatInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        sendChatBtn.click();
        e.preventDefault();
    }
});

function appendMessage(sender, message, typingEffect = false) {
    let messageDiv = document.createElement("div");
    messageDiv.classList.add("item", sender);

    let messageContent = document.createElement("div");
    messageContent.classList.add("msg");

    if (typingEffect && sender === "bot") {
        typeText(message, messageContent);
    } else {
        messageContent.innerHTML = `<p>${message}</p>`;
    }

    messageDiv.innerHTML = `
        <div class="icon">${sender === 'user' ? '😊' : '🤖'}</div>
    `;
    messageDiv.appendChild(messageContent);
    chatbox.appendChild(messageDiv);
    chatbox.scrollTop = chatbox.scrollHeight;
}

function typeText(text, container) {
    let index = 0;
    const typingSpeed = 10;
    let paragraph = document.createElement("p");
    container.appendChild(paragraph);

    function typeChar() {
        if (index < text.length) {
            paragraph.textContent += text.charAt(index);
            index++;
            setTimeout(typeChar, typingSpeed);
        } else {
            paragraph.textContent = text;
        }
    }

    typeChar();
}

function sendToBackend(message) {
    fetch('http://127.0.0.1:5000/chatbot', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message: message })
    })
        .then(response => response.json())
        .then(data => {
            const botMessage = data.response || "Sorry, no response!";
            appendMessage("bot", botMessage, true);

            // Show or hide deal buttons based on backend response
            if (data.show_buttons) {
                dealButtons.style.display = 'block';  // Show buttons if required
            } else {
                dealButtons.style.display = 'none';  // Hide buttons if not needed
            }
        })
        .catch(error => {
            console.error('Error:', error);
            appendMessage("bot", "Sorry, something went wrong!");
        });
}

// Deal and No Deal button event handlers
dealBtn.addEventListener("click", () => {
    appendMessage("user", "Deal!");
    sendToBackend("Deal!");  // Send "Deal!" message to the backend
    dealButtons.style.display = 'none';  // Hide buttons after selection
});

noDealBtn.addEventListener("click", () => {
    appendMessage("user", "No Deal!");
    sendToBackend("No Deal!");  // Send "No Deal!" message to the backend
    dealButtons.style.display = 'none';  // Hide buttons after selection
});
function initializeBackend(message) {
    fetch('http://127.0.0.1:5000/initialize', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message: message })
    })
        .then(response => response.json())
        .then(data => {
            const botMessage = data.response || "Sorry, no response!";
            appendMessage("bot", botMessage, true);  // Display the bot's response with typing effect
        })
        .catch(error => {
            console.error('Error:', error);
            appendMessage("bot", "Sorry, something went wrong!");  // Fallback message on error
        });
}

// Function to display the welcome message as a bot message on page load
document.addEventListener("DOMContentLoaded", function () {
    const welcomeText = "Hi!";
    initializeBackend(welcomeText);
});