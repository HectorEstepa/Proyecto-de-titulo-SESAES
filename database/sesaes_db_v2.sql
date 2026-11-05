--
-- PostgreSQL database dump
--

\restrict gxSDDxRinQ3LBfBpc22XO2mjauazKbIbO5TisW8gdYHW7OOhjXzvNagMTzUC8ix

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

-- Started on 2026-07-25 18:19:11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 6 (class 2615 OID 17353)
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

--
-- TOC entry 5058 (class 0 OID 0)
-- Dependencies: 6
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA public IS '';


--
-- TOC entry 2 (class 3079 OID 17454)
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- TOC entry 5060 (class 0 OID 0)
-- Dependencies: 2
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 235 (class 1259 OID 19458)
-- Name: auditoria; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auditoria (
    id integer NOT NULL,
    usuario_id integer,
    accion character varying,
    detalle character varying,
    entidad character varying,
    entidad_id integer,
    fecha timestamp without time zone DEFAULT now()
);


ALTER TABLE public.auditoria OWNER TO postgres;

--
-- TOC entry 234 (class 1259 OID 19457)
-- Name: auditoria_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auditoria_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.auditoria_id_seq OWNER TO postgres;

--
-- TOC entry 5061 (class 0 OID 0)
-- Dependencies: 234
-- Name: auditoria_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auditoria_id_seq OWNED BY public.auditoria.id;


--
-- TOC entry 227 (class 1259 OID 19359)
-- Name: cita; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cita (
    id integer NOT NULL,
    estudiante_id integer,
    profesional_id integer,
    fecha character varying,
    hora character varying,
    estado character varying DEFAULT 'pendiente'::character varying,
    observaciones character varying,
    motivo_cancelacion text,
    observaciones_atencion character varying,
    urgente boolean DEFAULT false,
    cancelada_por_admin boolean DEFAULT false,
    medicamento character varying
);


ALTER TABLE public.cita OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 19358)
-- Name: cita_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cita_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cita_id_seq OWNER TO postgres;

--
-- TOC entry 5062 (class 0 OID 0)
-- Dependencies: 226
-- Name: cita_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cita_id_seq OWNED BY public.cita.id;


--
-- TOC entry 239 (class 1259 OID 19496)
-- Name: configuracion_centro; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.configuracion_centro (
    id integer NOT NULL,
    nombre_centro character varying,
    direccion character varying,
    telefono character varying,
    correo_contacto character varying,
    horario_atencion character varying,
    foto_admin_url character varying,
    nombre_admin character varying
);


ALTER TABLE public.configuracion_centro OWNER TO postgres;

--
-- TOC entry 238 (class 1259 OID 19495)
-- Name: configuracion_centro_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.configuracion_centro_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.configuracion_centro_id_seq OWNER TO postgres;

--
-- TOC entry 5063 (class 0 OID 0)
-- Dependencies: 238
-- Name: configuracion_centro_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.configuracion_centro_id_seq OWNED BY public.configuracion_centro.id;


--
-- TOC entry 231 (class 1259 OID 19434)
-- Name: configuracion_sistema; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.configuracion_sistema (
    id integer NOT NULL,
    duracion_turno_min integer,
    agendamiento_por_pacientes boolean,
    cancelacion_instantanea boolean,
    sobreturnos_habilitados boolean,
    cupos_por_turno integer
);


ALTER TABLE public.configuracion_sistema OWNER TO postgres;

--
-- TOC entry 230 (class 1259 OID 19433)
-- Name: configuracion_sistema_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.configuracion_sistema_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.configuracion_sistema_id_seq OWNER TO postgres;

--
-- TOC entry 5064 (class 0 OID 0)
-- Dependencies: 230
-- Name: configuracion_sistema_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.configuracion_sistema_id_seq OWNED BY public.configuracion_sistema.id;


--
-- TOC entry 241 (class 1259 OID 19508)
-- Name: correo_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.correo_log (
    id integer NOT NULL,
    destinatario character varying,
    asunto character varying,
    cuerpo character varying,
    enviado boolean DEFAULT false,
    fecha timestamp without time zone DEFAULT now(),
    tipo character varying,
    referencia_id integer
);


ALTER TABLE public.correo_log OWNER TO postgres;

--
-- TOC entry 240 (class 1259 OID 19507)
-- Name: correo_log_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.correo_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.correo_log_id_seq OWNER TO postgres;

--
-- TOC entry 5065 (class 0 OID 0)
-- Dependencies: 240
-- Name: correo_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.correo_log_id_seq OWNED BY public.correo_log.id;


--
-- TOC entry 233 (class 1259 OID 19443)
-- Name: feriado; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.feriado (
    id integer NOT NULL,
    fecha character varying,
    descripcion character varying,
    creado_por integer
);


ALTER TABLE public.feriado OWNER TO postgres;

--
-- TOC entry 232 (class 1259 OID 19442)
-- Name: feriado_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.feriado_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.feriado_id_seq OWNER TO postgres;

--
-- TOC entry 5066 (class 0 OID 0)
-- Dependencies: 232
-- Name: feriado_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.feriado_id_seq OWNED BY public.feriado.id;


--
-- TOC entry 237 (class 1259 OID 19475)
-- Name: historial_estado_profesional; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.historial_estado_profesional (
    id integer NOT NULL,
    profesional_id integer,
    estado_anterior character varying,
    estado_nuevo character varying,
    motivo character varying,
    fecha timestamp without time zone,
    registrado_por integer
);


ALTER TABLE public.historial_estado_profesional OWNER TO postgres;

--
-- TOC entry 236 (class 1259 OID 19474)
-- Name: historial_estado_profesional_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.historial_estado_profesional_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.historial_estado_profesional_id_seq OWNER TO postgres;

--
-- TOC entry 5067 (class 0 OID 0)
-- Dependencies: 236
-- Name: historial_estado_profesional_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.historial_estado_profesional_id_seq OWNED BY public.historial_estado_profesional.id;


--
-- TOC entry 225 (class 1259 OID 19343)
-- Name: horario_disponible; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.horario_disponible (
    id integer NOT NULL,
    profesional_id integer,
    dia_nombre character varying,
    dia_num integer,
    fecha character varying,
    hora character varying,
    estado character varying
);


ALTER TABLE public.horario_disponible OWNER TO postgres;

--
-- TOC entry 224 (class 1259 OID 19342)
-- Name: horario_disponible_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.horario_disponible_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.horario_disponible_id_seq OWNER TO postgres;

--
-- TOC entry 5068 (class 0 OID 0)
-- Dependencies: 224
-- Name: horario_disponible_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.horario_disponible_id_seq OWNED BY public.horario_disponible.id;


--
-- TOC entry 229 (class 1259 OID 19416)
-- Name: notificacion; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notificacion (
    id integer NOT NULL,
    usuario_id integer,
    mensaje character varying,
    tipo character varying,
    leida boolean DEFAULT false,
    fecha_creacion timestamp without time zone DEFAULT now()
);


ALTER TABLE public.notificacion OWNER TO postgres;

--
-- TOC entry 228 (class 1259 OID 19415)
-- Name: notificacion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.notificacion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notificacion_id_seq OWNER TO postgres;

--
-- TOC entry 5069 (class 0 OID 0)
-- Dependencies: 228
-- Name: notificacion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.notificacion_id_seq OWNED BY public.notificacion.id;


--
-- TOC entry 223 (class 1259 OID 19327)
-- Name: profesional; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.profesional (
    id integer NOT NULL,
    nombre character varying,
    especialidad character varying,
    iniciales character varying(5),
    descripcion character varying,
    usuario_id integer,
    duracion_min integer DEFAULT 45,
    estado character varying DEFAULT 'activo'::character varying,
    correo character varying,
    rut character varying,
    foto_url character varying
);


ALTER TABLE public.profesional OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 19326)
-- Name: profesional_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.profesional_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.profesional_id_seq OWNER TO postgres;

--
-- TOC entry 5070 (class 0 OID 0)
-- Dependencies: 222
-- Name: profesional_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.profesional_id_seq OWNED BY public.profesional.id;


--
-- TOC entry 221 (class 1259 OID 19315)
-- Name: usuario; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.usuario (
    id integer NOT NULL,
    correo character varying,
    password character varying,
    rol character varying,
    foto_url text,
    telefono character varying,
    nombre character varying,
    tema_oscuro boolean DEFAULT false,
    carrera character varying,
    rut character varying,
    activo boolean DEFAULT true
);


ALTER TABLE public.usuario OWNER TO postgres;

--
-- TOC entry 220 (class 1259 OID 19314)
-- Name: usuario_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.usuario_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.usuario_id_seq OWNER TO postgres;

--
-- TOC entry 5071 (class 0 OID 0)
-- Dependencies: 220
-- Name: usuario_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.usuario_id_seq OWNED BY public.usuario.id;


--
-- TOC entry 4859 (class 2604 OID 19461)
-- Name: auditoria id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auditoria ALTER COLUMN id SET DEFAULT nextval('public.auditoria_id_seq'::regclass);


--
-- TOC entry 4850 (class 2604 OID 19362)
-- Name: cita id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cita ALTER COLUMN id SET DEFAULT nextval('public.cita_id_seq'::regclass);


--
-- TOC entry 4862 (class 2604 OID 19499)
-- Name: configuracion_centro id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.configuracion_centro ALTER COLUMN id SET DEFAULT nextval('public.configuracion_centro_id_seq'::regclass);


--
-- TOC entry 4857 (class 2604 OID 19437)
-- Name: configuracion_sistema id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.configuracion_sistema ALTER COLUMN id SET DEFAULT nextval('public.configuracion_sistema_id_seq'::regclass);


--
-- TOC entry 4863 (class 2604 OID 19511)
-- Name: correo_log id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.correo_log ALTER COLUMN id SET DEFAULT nextval('public.correo_log_id_seq'::regclass);


--
-- TOC entry 4858 (class 2604 OID 19446)
-- Name: feriado id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feriado ALTER COLUMN id SET DEFAULT nextval('public.feriado_id_seq'::regclass);


--
-- TOC entry 4861 (class 2604 OID 19478)
-- Name: historial_estado_profesional id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.historial_estado_profesional ALTER COLUMN id SET DEFAULT nextval('public.historial_estado_profesional_id_seq'::regclass);


--
-- TOC entry 4849 (class 2604 OID 19346)
-- Name: horario_disponible id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.horario_disponible ALTER COLUMN id SET DEFAULT nextval('public.horario_disponible_id_seq'::regclass);


--
-- TOC entry 4854 (class 2604 OID 19419)
-- Name: notificacion id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notificacion ALTER COLUMN id SET DEFAULT nextval('public.notificacion_id_seq'::regclass);


--
-- TOC entry 4846 (class 2604 OID 19330)
-- Name: profesional id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.profesional ALTER COLUMN id SET DEFAULT nextval('public.profesional_id_seq'::regclass);


--
-- TOC entry 4843 (class 2604 OID 19318)
-- Name: usuario id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario ALTER COLUMN id SET DEFAULT nextval('public.usuario_id_seq'::regclass);


--
-- TOC entry 4887 (class 2606 OID 19467)
-- Name: auditoria auditoria_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auditoria
    ADD CONSTRAINT auditoria_pkey PRIMARY KEY (id);


--
-- TOC entry 4877 (class 2606 OID 19367)
-- Name: cita cita_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cita
    ADD CONSTRAINT cita_pkey PRIMARY KEY (id);


--
-- TOC entry 4893 (class 2606 OID 19504)
-- Name: configuracion_centro configuracion_centro_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.configuracion_centro
    ADD CONSTRAINT configuracion_centro_pkey PRIMARY KEY (id);


--
-- TOC entry 4882 (class 2606 OID 19440)
-- Name: configuracion_sistema configuracion_sistema_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.configuracion_sistema
    ADD CONSTRAINT configuracion_sistema_pkey PRIMARY KEY (id);


--
-- TOC entry 4896 (class 2606 OID 19518)
-- Name: correo_log correo_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.correo_log
    ADD CONSTRAINT correo_log_pkey PRIMARY KEY (id);


--
-- TOC entry 4885 (class 2606 OID 19451)
-- Name: feriado feriado_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feriado
    ADD CONSTRAINT feriado_pkey PRIMARY KEY (id);


--
-- TOC entry 4890 (class 2606 OID 19483)
-- Name: historial_estado_profesional historial_estado_profesional_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.historial_estado_profesional
    ADD CONSTRAINT historial_estado_profesional_pkey PRIMARY KEY (id);


--
-- TOC entry 4874 (class 2606 OID 19351)
-- Name: horario_disponible horario_disponible_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.horario_disponible
    ADD CONSTRAINT horario_disponible_pkey PRIMARY KEY (id);


--
-- TOC entry 4880 (class 2606 OID 19426)
-- Name: notificacion notificacion_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notificacion
    ADD CONSTRAINT notificacion_pkey PRIMARY KEY (id);


--
-- TOC entry 4872 (class 2606 OID 19335)
-- Name: profesional profesional_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.profesional
    ADD CONSTRAINT profesional_pkey PRIMARY KEY (id);


--
-- TOC entry 4869 (class 2606 OID 19323)
-- Name: usuario usuario_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT usuario_pkey PRIMARY KEY (id);


--
-- TOC entry 4888 (class 1259 OID 19473)
-- Name: ix_auditoria_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_auditoria_id ON public.auditoria USING btree (id);


--
-- TOC entry 4878 (class 1259 OID 19378)
-- Name: ix_cita_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_cita_id ON public.cita USING btree (id);


--
-- TOC entry 4894 (class 1259 OID 19505)
-- Name: ix_configuracion_centro_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_configuracion_centro_id ON public.configuracion_centro USING btree (id);


--
-- TOC entry 4883 (class 1259 OID 19441)
-- Name: ix_configuracion_sistema_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_configuracion_sistema_id ON public.configuracion_sistema USING btree (id);


--
-- TOC entry 4891 (class 1259 OID 19494)
-- Name: ix_historial_estado_profesional_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_historial_estado_profesional_id ON public.historial_estado_profesional USING btree (id);


--
-- TOC entry 4875 (class 1259 OID 19357)
-- Name: ix_horario_disponible_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_horario_disponible_id ON public.horario_disponible USING btree (id);


--
-- TOC entry 4870 (class 1259 OID 19341)
-- Name: ix_profesional_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_profesional_id ON public.profesional USING btree (id);


--
-- TOC entry 4866 (class 1259 OID 19324)
-- Name: ix_usuario_correo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_usuario_correo ON public.usuario USING btree (correo);


--
-- TOC entry 4867 (class 1259 OID 19325)
-- Name: ix_usuario_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_usuario_id ON public.usuario USING btree (id);


--
-- TOC entry 4903 (class 2606 OID 19468)
-- Name: auditoria auditoria_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auditoria
    ADD CONSTRAINT auditoria_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuario(id);


--
-- TOC entry 4899 (class 2606 OID 19368)
-- Name: cita cita_estudiante_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cita
    ADD CONSTRAINT cita_estudiante_id_fkey FOREIGN KEY (estudiante_id) REFERENCES public.usuario(id);


--
-- TOC entry 4900 (class 2606 OID 19373)
-- Name: cita cita_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cita
    ADD CONSTRAINT cita_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesional(id);


--
-- TOC entry 4902 (class 2606 OID 19452)
-- Name: feriado feriado_creado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feriado
    ADD CONSTRAINT feriado_creado_por_fkey FOREIGN KEY (creado_por) REFERENCES public.usuario(id);


--
-- TOC entry 4904 (class 2606 OID 19484)
-- Name: historial_estado_profesional historial_estado_profesional_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.historial_estado_profesional
    ADD CONSTRAINT historial_estado_profesional_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesional(id);


--
-- TOC entry 4905 (class 2606 OID 19489)
-- Name: historial_estado_profesional historial_estado_profesional_registrado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.historial_estado_profesional
    ADD CONSTRAINT historial_estado_profesional_registrado_por_fkey FOREIGN KEY (registrado_por) REFERENCES public.usuario(id);


--
-- TOC entry 4898 (class 2606 OID 19352)
-- Name: horario_disponible horario_disponible_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.horario_disponible
    ADD CONSTRAINT horario_disponible_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesional(id);


--
-- TOC entry 4901 (class 2606 OID 19427)
-- Name: notificacion notificacion_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notificacion
    ADD CONSTRAINT notificacion_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuario(id);


--
-- TOC entry 4897 (class 2606 OID 19336)
-- Name: profesional profesional_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.profesional
    ADD CONSTRAINT profesional_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuario(id);


--
-- TOC entry 5059 (class 0 OID 0)
-- Dependencies: 6
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


-- Completed on 2026-07-25 18:19:11

--
-- PostgreSQL database dump complete
--

\unrestrict gxSDDxRinQ3LBfBpc22XO2mjauazKbIbO5TisW8gdYHW7OOhjXzvNagMTzUC8ix

