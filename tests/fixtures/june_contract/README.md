# June contract fixtures

The fixed sample messages of spec 004's J16, with synthetic values only. Each side's contract tests load these
files, so a change here changes the tests of both sides. The signed body of `result_message.json` is its `body`
as compact JSON with sorted keys, and the tests build the shared secret while they run.
