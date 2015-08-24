API Application
===============

Checkout
--------

.. code:: bash

   git clone ...

Build
-----

.. code:: bash

   cd app_api
   make -f config/dev install

Run the application
-------------------

.. code:: bash

   cd app_api
   make -f config/dev serve

Open your browser at http://localhost:6543/ or http://localhost:6543/?debug (debug mode).

Available actions may be listed using:

.. code:: bash

   cd app_api
   make help
