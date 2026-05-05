on run argv
    set chatId to item 1 of argv
    set messageText to item 2 of argv
    tell application "Messages"
        send messageText to text chat id chatId
    end tell
end run
