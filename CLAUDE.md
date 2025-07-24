Use the makefile for all development commands.
The following targets are available:

Before doing anything, you have to activate the virtual environment with

```
. .venv/bin/activate
```

The `.venv/` directory lives in the root `intherock.ai/` folder.

Once activated, then you can run the following:

```
make help # see what's available
make install # updates any dependencies
make api # runs the api
```

All new packages must first be added to the requirements.txt file, then you run `make install` to sync your dependencies.
