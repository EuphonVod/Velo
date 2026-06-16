try:
    from PIL import ImageGrab
    img = ImageGrab.grab()
    print("OK, taille:", img.size)
except Exception as e:
    print("erreur:", e)