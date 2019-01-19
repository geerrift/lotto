
out/main.js: src/main.elm
	elm make src/main.elm --output=../backend/app/static/main.js
	#elm make --optimize src/main.elm --output=../backend/app/static/main.js
	#uglifyjs ../backend/app/static/main.js --compress 'pure_funcs="F2,F3,F4,F5,F6,F7,F8,F9,A2,A3,A4,A5,A6,A7,A8,A9",pure_getters,keep_fargs=false,unsafe_comps,unsafe' | uglifyjs --mangle --output=../backend/app/static/main.min.js
