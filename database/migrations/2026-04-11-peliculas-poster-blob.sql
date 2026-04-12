ALTER TABLE peliculas
    ADD COLUMN poster_blob MEDIUMBLOB NULL AFTER imagen_url,
    ADD COLUMN poster_mime VARCHAR(100) NULL AFTER poster_blob;
