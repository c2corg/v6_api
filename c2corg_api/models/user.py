import bcrypt

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String
    )

from c2corg_api.models import Base, users_schema


class User(Base):
    """
    Class containing the users' private and authentication data.
    """
    __tablename__ = 'user'
    __table_args__ = {"schema": users_schema}

    id = Column(Integer, primary_key=True)
    username = Column(String(200), nullable=False, unique=True)
    email = Column(String(200), nullable=False, unique=True)
    email_validated = Column(Boolean, nullable=False)
    _password = Column("password", String(255), nullable=False)
    temp_password = Column(String(255))

    def _get_password(self):
        return self._password

    def _set_password(self, password):
        self._password = self.__encrypt_password(password)

    def set_temp_password(self, password):
        self.temp_password = self.__encrypt_password(password)

    def __encrypt_password(self, password):
        return bcrypt.hashpw(password, bcrypt.gensalt())

    def validate_password(self, passwd):
        """Check the password against existing credentials.
        this method _MUST_ return a boolean.
        @param passwd: the password that was provided by the user to
        try and authenticate. This is the clear text version that we will
        need to match against the encrypted one in the database.
        @type password: string
        """
        if self._password == bcrypt.hashpw(passwd, self._password):
            return True
        if self.temp_password is not None and \
           self.temp_password != "" and \
           self.temp_password == bcrypt.hashpw(passwd, self.temp_password):
            self._password = self.temp_password
            self.temp_password = None
            return True
        return False

    password = property(_get_password, _set_password)
