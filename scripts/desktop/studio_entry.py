"""Frozen portable control entry; model runtimes are never bundled."""
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--studio-supervise':
        sys.argv.pop(1)
        from ailab_studio.workers.supervisor import main
        sys.exit(main())
    from ailab_studio.__main__ import main
    main()
