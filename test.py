import sys
import pytest

def main():
    a=["--maxfail=1","-v"]
    sys.exit(pytest.main(a))

if __name__=="__main__":
    main()
