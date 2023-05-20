
let run = function() {

    // Connect to the Socket.IO server
    var socket = io.connect();


    // Handle the 'connect' event
    socket.on('connect', function() {
        messages.innerHTML = '';
        console.log('Connected to the server');

    });


    function scrollToBottom(messages) {
        messages.scrollTop = messages.scrollHeight;
    }

    // Create a MutationObserver to watch for changes in the messages div
    var messagesObserver = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                var messages = document.getElementById('messages');
                scrollToBottom(messages);
            }
        });
    });

    let messages = document.getElementById('messages');
    messagesObserver.observe(messages, { childList: true });

    let doTimestamp = function() {
        let now = new Date();
        return '<div style="color: #c0c0f0">' + now.toLocaleString() + ': </div>';
    }

    let doMessage = function(color,message) {

        if (!color) {
            color = "#c0c0f0"
        }

        messages.innerHTML += "<div style='white-space:pre; display:flex;flex-direction:row;align-items:center'>" + doTimestamp() + '<p style="padding-left:1ch; color:' + color + '">' + message + '</p></div>';
    }

    // Handle the 'message' event
    socket.on('message', function(data) {
        console.log("Got server message: " + data)
        doMessage("#fff", data)
    });

    socket.on('warn', function(data) {
        console.log("Got server warning: " + data)
        doMessage("#FFFF00", data)
    });

    socket.on('error', function(data) {
        console.log("Got server error: " + data)
        doMessage("#F00", data)
    });

    socket.on('input', function(data) {
        console.log("Got user input: " + data)
        doMessage(null, data)
    });

    socket.on('attention', function(data) {
        console.log("Got server attention: " + data)
        doMessage("#00D8D8", data)
    });

    // Handle the 'reply' event
    socket.on('reply', function(data) {
        console.log("Got server reply: " + data)
        doMessage("#fff", data)
    });

    // Send a message to the server when the send button is clicked
    var sendButton = document.getElementById('send-button');
    sendButton.addEventListener('click', function() {
        let messageInput = document.getElementById('message-input');
        sendMessage()
        messageInput.focus();
    });


    // Add an event listener for the 'keydown' event on the message-input element.
    document.getElementById('message-input').addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            sendMessage();
        }
    });

    let replyPending

    // Send a message to the server
    function sendMessage() {

        let messageInput = document.getElementById('message-input');
        let message = messageInput.value;
        messageInput.value = '';
        if (replyPending) {

            const response = {
                handle: replyPending,
                data: message,
                error: null
            };

            replyPending = null;
            socket.emit('remote_reply', JSON.stringify(response));


        } else {
            console.log("Sending regular message: " + message);
            socket.emit('message', message);
        }

    }

    socket.on('remote_request', function(msg) {
        console.log('Received remote request');

        const {command, data, handle} = JSON.parse(msg);

        console.log('Command:', command);
        console.log('Data:', data);
        console.log('Handle:', handle);

        // Perform the desired action based on the received command and data.
        // In this example, we simply echo back the received data

        doMessage("#fff", command)

        replyPending = handle;
    });

    socket.on('title', function(msg) {
        document.getElementById("title")
        title.innerText = msg
    })

    const eventSource = new EventSource('/updates');

    eventSource.onmessage = function(event) {
        console.log("Got server event", event)
        doMessage("#fff", event.data)
    };

}



document.addEventListener('DOMContentLoaded', function() {
    run();
});
