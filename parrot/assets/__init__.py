from pathlib import Path


with Path("parrot/assets/failure_phrases.txt").open() as f:
	failure_phrases = f.readlines()

with Path("parrot/assets/sunshine_script.txt").open() as f:
	sunshine_script = f.read()

noki_png = "parrot/assets/noki.png"
