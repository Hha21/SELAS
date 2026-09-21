# external/

Third-party material we read but do not ship: reference codebases, and the TeX
of papers whose protocol we are following.

**Contents are gitignored.** This repository is the paper's public artifact, so
vendoring someone else's code into it raises licensing questions we do not need
to answer, and the files are large and reconstructable from their own source.
What belongs in our tree is our implementation of a protocol plus a citation,
not a copy of the thing we are citing.

So: read from here, write into `experiments/`.

```
external/
  <project>/            cloned repo, left as-is
  <project>-paper/      TeX or PDF of the paper defining the protocol
```

If something here turns out to be needed at runtime -- a released checkpoint, a
fixed dataset -- that is a different case, and it should be pinned by URL and
hash in the code that uses it rather than committed here.
