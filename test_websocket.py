try:
    from PIL import ImageGrab
    img = ImageGrab.grab()
    print("✓ Capture écran OK, taille:", img.size)
except Exception as e:
    print("✗ Erreur:", e)