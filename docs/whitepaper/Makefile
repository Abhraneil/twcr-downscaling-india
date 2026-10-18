# White paper: tables from results/, then the PDF.   make   |   make clean
whitepaper.pdf: whitepaper.tex refs.bib tables/.stamp
	latexmk -pdf -interaction=nonstopmode -halt-on-error whitepaper.tex

tables/.stamp: make_tables.py ../../results/SCORECARD.md ../../results/HYPOTHESES.md $(wildcard ../../results/scores.csv)
	python3 make_tables.py && touch $@

clean:
	latexmk -C whitepaper.tex; rm -f tables/.stamp
