FROM postgres:17.11

RUN mkdir -p /backups/db /backups/media \
    && chmod 1777 /backups /backups/db /backups/media

COPY scripts/backup.sh scripts/restore.sh /usr/local/bin/
RUN sed -i 's/\r$//' /usr/local/bin/backup.sh /usr/local/bin/restore.sh \
    && chmod 755 /usr/local/bin/backup.sh /usr/local/bin/restore.sh

ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup.sh"]
