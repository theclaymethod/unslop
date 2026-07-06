# qgrep

Grep, but it understands quotes. That's the whole pitch. Regular grep will happily match inside string literals and comments, which is fine until you're trying to find every actual call to `delete_user` and half your hits are in a changelog.

## install

```
go install github.com/mmn/qgrep@latest
```

Needs Go 1.21+. There's no Homebrew formula yet. I keep meaning to.

## usage

```
qgrep 'delete_user' ./src
```

By default it skips matches inside string literals and line comments for C-family, Python, Go, and Ruby. Everything else it treats as plain text and falls back to normal grep behavior, so don't expect magic in your COBOL.

Flags:

- `-s` also search inside strings (i.e. give up and act like grep)
- `-c` also search inside comments
- `--lang=X` force a language instead of guessing from extension

The language guessing is dumb. It looks at the file extension and nothing else. If you have `.h` files that are actually C++ it'll parse them as C and occasionally get a `<` wrong. Patches welcome, I don't write much C++ anymore so I haven't cared enough to fix it.

## why

I wrote this on a Sunday because I was annoyed. It is not battle-tested. It has one contributor (me) and about 60% test coverage, all of it on the tokenizer because that's the part that breaks. If you hit a parsing bug, open an issue with the smallest file that reproduces it and I'll usually get to it within a week or two.

No license file yet. Assume MIT, I'll add it properly when I'm not lazy.
