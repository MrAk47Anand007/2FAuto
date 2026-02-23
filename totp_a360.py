import pyotp
import sys

def get_totp(secret_key: str) -> str:
    """
    Takes secret key as input and returns current TOTP code
    """
    secret = secret_key.strip().replace(" ", "")
    totp = pyotp.TOTP(secret)
    return totp.now()

# A360 passes arguments via command line
if __name__ == "__main__":
    secret_key = sys.argv[1]  # A360 passes secret key as first argument
    otp = get_totp(secret_key)
    print(otp)  # A360 captures stdout as output