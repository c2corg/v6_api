package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._

class ConsultationForumAnonyme extends Simulation {

	val httpProtocol = http
		.baseURL(C2corgConf.forum_url)
                .inferHtmlResources(C2corgConf.black_list, WhiteList())
		.acceptHeader("application/json, text/javascript, */*; q=0.01")
		.acceptEncodingHeader("gzip, deflate")
		.acceptLanguageHeader("fr-CH,en-US;q=0.7,en;q=0.3")
		.userAgentHeader("Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:49.0) Gecko/20100101 Firefox/49.0")

	val scn = scenario("ConsultationForumAnonyme")
		.exec(Forum.init)
		.pause(1)
                .exec(Forum.open)
		.pause(6)
                .exec(Forum.scroll)
		.pause(8)
                .exec(Forum.scroll)
		.pause(1)
                .exec(Topic.open)
		.pause(24)
                .exec(Topic.scroll)

        setUp(scn.inject(rampUsers(C2corgConf.num_users) over (C2corgConf.ramp_time_seconds seconds))).protocols(httpProtocol)
}
