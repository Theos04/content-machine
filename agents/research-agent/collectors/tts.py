from gtts import gTTS

text = """
Look at you. Holding your 1,200 dollar flagship smartphone. You think you’re a tech god because you set up a custom wallpaper and know how to clear your app cache. You watch Mr. Robot once, and suddenly you want to "penetrate the mainframe" and get free Wi-Fi from the Starbucks down the street."""

tts = gTTS(text=text, lang='en', slow=False)
tts.save("output.mp3")

print("Saved as output.mp3")
