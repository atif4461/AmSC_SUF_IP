

make-dev-image:
	podman build . -f amsc_dev.Containerfile --cap-add sys_ptrace -t amsc_dev

make-dev-toolbox:
	toolbox create --image=amsc_dev amsc

clear-dev-toolbox:
	podman stop -i amsc
	toolbox rm amsc



