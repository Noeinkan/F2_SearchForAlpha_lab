"""The research workspace as a hosted product site (alpha.noeinsolutions.com).

Not the public demo (``demo/``): this is the full workspace -- live Yahoo and
SEC data, the Flow Scanner, every optimiser -- for one person, behind the
owner's login. The broker path is absent from the image, as in the demo.

- ``login``    the email + password gate in front of every page and callback
- ``persist``  points state/, results/, export/ and the user-owned config
               files at the data volume, so they survive a redeploy
- ``server``   the WSGI entry point (``python -m hosted.server``)

See ``docs/HOSTED.md``.
"""
