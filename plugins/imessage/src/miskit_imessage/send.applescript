on wait_until_running(app_name, delay_seconds)
    repeat until application app_name is running
        delay delay_seconds
    end repeat

    delay delay_seconds
end wait_until_running

on direct_recipient(target_id)
    if target_id does not contain ";" then
        return target_id
    end if

    set previous_delimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to ";"
    set parts to text items of target_id
    set AppleScript's text item delimiters to previous_delimiters

    if (count of parts) is not 3 then
        error "Unsupported Messages target: " & target_id
    end if

    if item 2 of parts is not "-" then
        error "Group chat targets are not supported by the iMessage sender."
    end if

    return item 3 of parts
end direct_recipient

on run argv
    set targetId to item 1 of argv
    set messageText to item 2 of argv

    tell application "Messages"
        if it is not running then
            launch
        end if
    end tell

    my wait_until_running("Messages", 0.2)

    tell application "Messages"
        set recipientHandle to my direct_recipient(targetId)
        set targetService to id of 1st service whose service type = iMessage
        set targetBuddy to buddy recipientHandle of service id targetService
        send messageText to targetBuddy
    end tell
end run
